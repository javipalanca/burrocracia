import calendar
import datetime
import random

import pandas as pd

MAX_HOUR_DAY = 7.5


def get_working_days(_first_date, _last_date):
	"""Returns a list of the working days in a range of dates"""
	_working_days = []
	for date in pd.date_range(_first_date, _last_date):
		if date.dayofweek < 5:
			_working_days.append(date.strftime("%-d/%-m/%y"))
	return _working_days


def read_df(_filename):
	_df = pd.read_csv(_filename, encoding='iso-8859-1', sep=';')
	first_day, first_month, first_year = _df.columns[7].split('/')
	first_date = datetime.date(year=int(first_year) + 2000, month=int(first_month), day=int(first_day))
	last_day, last_month, last_year = _df.columns[-1].split('/')
	last_date = datetime.date(year=int(last_year) + 2000, month=int(last_month), day=int(last_day))
	_working_days = get_working_days(first_date, last_date)
	_num_working_days = len(_working_days)

	return _df, _working_days, _num_working_days


def cli_questions(_df, _hours_by_project):
	for index, row in _df.iterrows():
		if row["Id Actividad"] == 92:
			project = row["Proyecto"]
			wp = int(row["Working Package"])
			if wp != -1:
				hours = input(f"Cuantas horas deseas imputar al WP {wp} del proyecto {project} (-1 si no hay mínimo): ")
				_hours_by_project[project, wp] = int(hours)
			else:
				hours = input(f"Cuantas horas deseas imputar al proyecto {project} (-1 si no hay mínimo): ")
				_hours_by_project[project, -1] = int(hours)
	_teaching_hours = float(
		input("Cuantas horas mínimas al día deseas imputar a la actividad de docencia (-1 si no hay mínimo): "))

	return _hours_by_project, _teaching_hours


def generate_questions(_df):
	questions = {}
	for index, row in _df.iterrows():
		if row["Id Actividad"] == 92:
			project = row["Proyecto"]
			wp = int(row["Working Package"])
			if wp != -1:
				questions[project, wp] = f"Cuantas horas deseas imputar al WP {wp} del proyecto {project} (-1 si no hay mínimo): "
			else:
				questions[project, -1] = f"Cuantas horas deseas imputar al proyecto {project} (-1 si no hay mínimo): "

	questions[
		"__teaching__", -1] = "Cuantas horas mínimas al día deseas imputar a la actividad de docencia (-1 si no hay mínimo): "

	return questions


def solve_hours(_df, _hours_by_project, _working_days):
	# iter dataframe by rows
	for index, row in _df.iterrows():
		project, wp = row['Proyecto'], row['Working Package']
		if (project, wp) not in _hours_by_project:
			continue
		if _hours_by_project[(project, wp)] == -1:
			continue
		while _hours_by_project[(project, wp)] > 0:
			for _day in _working_days:
				pending_hours_in_day = MAX_HOUR_DAY - _df[_day].sum()
				new_hours = min(min(1, _hours_by_project[(project, wp)]), pending_hours_in_day)
				# update dataframe
				_df.loc[index, _day] = _df.loc[index, _day] + new_hours
				_hours_by_project[(project, wp)] -= new_hours
	# projects without min hours restriction
	projects_without_restriction = [key for key, value in _hours_by_project.items() if value == -1]
	for _day in _working_days:
		if len(projects_without_restriction) != 0:
			project = random.choice(projects_without_restriction)
			pending_hours_in_day = MAX_HOUR_DAY - _df[_day].sum()
			# locate by two columns and row in df
			_df.loc[(_df['Proyecto'] == project[0]) & (_df['Working Package'] == project[1]), _day] = pending_hours_in_day

		_df[_day] = _df[_day].apply(lambda x: str(x).replace('.', ',') if x != 0.0 else '')

	return _df


def check_hours(_df, _working_days, _num_working_days, _teaching_hours, _hours_by_project):
	used_hours = 0
	# set df columns to float type with default value 0
	for day in _working_days:
		_df[day] = _df[day].apply(lambda x: float(str(x).replace(',', '.')))
		_df[day] = _df[day].astype(float).fillna(0)
		if _teaching_hours != -1:
			# put in row "Docencia" and column day the max value between the current value and teaching_hours
			_df.loc[_df['Id Actividad'] == 97, day] = _df.loc[_df['Id Actividad'] == 97, day].apply(lambda x: max(x, _teaching_hours))

		used_hours += _df[day].sum()
	max_hours_month = MAX_HOUR_DAY * _num_working_days - used_hours
	if sum([x for x in _hours_by_project.values() if x != -1]) > max_hours_month:
		total_teaching_hours = _df.loc[_df['Id Actividad'] == 97, _df.columns[7:]].sum(axis=1)
		msg = f"Te has pasado de horas.\nEl máximo es de 7.5h al día y {max_hours_month} horas este mes (sin contar la docencia).\n"
		msg += f"Has asignado {total_teaching_hours.sum()} horas de docencia"
		raise Exception(msg)

	return _df


if __name__ == '__main__':
	# load csv to dataframe with iso-8859-1 encoding
	filename = "/Users/jpalanca/Downloads/Horas_Participante.csv"
	df, working_days, num_working_days = read_df(filename)

	hours_by_project = {}

	hours_by_project, teaching_hours = cli_questions(df, hours_by_project)

	df = check_hours(df, working_days, num_working_days, teaching_hours, hours_by_project)

	df = solve_hours(df, hours_by_project, working_days)

	df.to_csv('/Users/jpalanca/Downloads/output.csv', index=False, sep=";", encoding='iso-8859-1')
