import datetime
import random

import dateutil.parser as parser
import pandas as pd

MAX_HOUR_DAY = 7.5


class SolverException(Exception):
	pass


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
	first_year = '20' + first_year if len(first_year) == 2 else first_year
	first_date = datetime.date(year=int(first_year), month=int(first_month), day=int(first_day))
	last_day, last_month, last_year = _df.columns[-1].split('/')
	last_year = '20' + last_year if len(last_year) == 2 else last_year
	last_date = datetime.date(year=int(last_year), month=int(last_month), day=int(last_day))
	_working_days = get_working_days(first_date, last_date)
	_num_working_days = len(_working_days)

	columns = _df.columns[7:]
	columns = [parser.parse(x, dayfirst=True).strftime("%-d/%-m/%y") for x in columns]
	_df.columns = _df.columns[:7].tolist() + columns

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
		if row["Id Actividad"] not in [97, 98, 99, 100, 108]:
			project = row["Proyecto"]
			wp = int(row["Working Package"])
			if wp != -1:
				questions[project, wp] = f"Cuantas horas deseas imputar al WP {wp} del proyecto {project} (-1 si no hay mínimo): "
			else:
				questions[project, -1] = f"Cuantas horas deseas imputar al proyecto {project} (-1 si no hay mínimo): "

	if len(questions) == 0:
		questions["__empty__", -1] = "No se han encontrado proyectos de investigación en el fichero CSV."
	questions[
		"__teaching__", -1] = "Cuantas horas mínimas al DÍA deseas imputar a la DOCENCIA (-1 si no hay mínimo): "
	questions[
		"__other_id__", -1] = "Cuantas horas mínimas al DÍA deseas imputar a OTRAS ACTIVIDADES DE I+D (-1 si no hay mínimo): "
	questions[
		"__other__", -1] = "Cuantas horas mínimas al DÍA deseas imputar a OTRAS ACTIVIDADES (-1 si no hay mínimo): "
	questions[
		"__lessons__", -1] = "Cuantas horas mínimas al DÍA deseas imputar a la FORMACIÓN DEL PARTICIPANTE (-1 si no hay mínimo): "

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

	return _df


def transform_df_to_str_types(_df, _working_days):
	for _day in _working_days:
		_df[_day] = _df[_day].apply(lambda x: str(x).replace('.', ',') if x != 0.0 else '')
	return _df


def check_hours(_df, _working_days, _num_working_days, _other_activities, _hours_by_project):
	used_hours = 0
	# set df columns to float type with default value 0
	activities = {"__teaching__": 97, "__other_id__": 98, "__other__": 100, "__lessons__": 108}
	for day in _working_days:
		_df[day] = _df[day].apply(lambda x: float(str(x).replace(',', '.')))
		_df[day] = _df[day].astype(float).fillna(0)
		for activity, value in _other_activities.items():
			if value != -1:
				pending_hours_in_day = MAX_HOUR_DAY - _df[day].sum()
				# put in row "Docencia" and column day the max value between the current value and teaching_hours
				_df.loc[_df['Id Actividad'] == activities[activity], day] = _df.loc[
					_df['Id Actividad'] == activities[activity], day].apply(lambda x: max(x, min(max(x, value), pending_hours_in_day)))

		used_hours += _df[day].sum()
	max_hours_month = MAX_HOUR_DAY * _num_working_days - used_hours
	if sum([x for x in _hours_by_project.values() if x != -1]) > max_hours_month:
		total_teaching_hours = _df.loc[_df['Id Actividad'] == 97, _df.columns[7:]].sum(axis=1).sum()
		total_other_id_hours = _df.loc[_df['Id Actividad'] == 98, _df.columns[7:]].sum(axis=1).sum()
		total_other_hours = _df.loc[_df['Id Actividad'] == 100, _df.columns[7:]].sum(axis=1).sum()
		total_lessons_hours = _df.loc[_df['Id Actividad'] == 108, _df.columns[7:]].sum(axis=1).sum()
		msg = f"Te has pasado de horas.\nEl máximo es de 7.5h al día y {max_hours_month} horas este mes.\n"
		if total_teaching_hours > 0:
			msg += f"Has asignado {total_teaching_hours} horas de docencia\n"
		if total_other_id_hours > 0:
			msg += f"Has asignado {total_other_id_hours} horas de otras actividades de I+D\n"
		if total_other_hours > 0:
			msg += f"Has asignado {total_other_hours} horas de otras actividades\n"
		if total_lessons_hours > 0:
			msg += f"Has asignado {total_lessons_hours} horas de formación del participante\n"
		raise SolverException(msg)

	return _df


if __name__ == '__main__':
	# load csv to dataframe with iso-8859-1 encoding
	filename = "/Users/jpalanca/Downloads/Horas_Participante.csv"
	df, working_days, num_working_days = read_df(filename)

	hours_by_project = {}

	hours_by_project, teaching_hours = cli_questions(df, hours_by_project)

	df = check_hours(df, working_days, num_working_days, teaching_hours, hours_by_project)

	df = solve_hours(df, hours_by_project, working_days)

	df = transform_df_to_str_types(df, working_days)

	df.to_csv('/Users/jpalanca/Downloads/output.csv', index=False, sep=";", encoding='iso-8859-1')
