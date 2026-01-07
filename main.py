import datetime
import io
import os
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


def read_df(_file):
	_df = pd.read_csv(_file, encoding='iso-8859-1', sep=';')
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
	# For testing, assign fixed values
	for index, row in _df.iterrows():
		if row["Id Actividad"] == 92:
			project = row["Proyecto"]
			wp = int(row["Working Package"])
			if wp != -1:
				_hours_by_project[project, wp] = 10  # Assign 10 hours for testing
			else:
				_hours_by_project[project, -1] = -1  # No minimum
	_other_activities = {
		"__teaching__": 2.0,  # Fixed for testing
		"__other_id__": -1,
		"__other__": -1,
		"__lessons__": -1
	}

	return _hours_by_project, _other_activities


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


def solve_hours(_df, _hours_by_project, _working_days, daily_max=MAX_HOUR_DAY):
	# iter dataframe by rows
	for index, row in _df.iterrows():
		project, wp = row['Proyecto'], row['Working Package']
		if (project, wp) not in _hours_by_project:
			continue
		if _hours_by_project[(project, wp)] == -1:
			continue
		while _hours_by_project[(project, wp)] > 0:
			for _day in _working_days:
				pending_hours_in_day = daily_max - _df[_day].sum()
				new_hours = min(min(1, _hours_by_project[(project, wp)]), pending_hours_in_day)
				# update dataframe
				_df.loc[index, _day] = _df.loc[index, _day] + new_hours
				_hours_by_project[(project, wp)] -= new_hours
	# projects without min hours restriction
	projects_without_restriction = [key for key, value in _hours_by_project.items() if value == -1]
	for _day in _working_days:
		if len(projects_without_restriction) != 0:
			project = random.choice(projects_without_restriction)
			pending_hours_in_day = daily_max - _df[_day].sum()
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

	# allow overrides for daily/weekly caps via env vars
	daily_cap = float(os.environ.get('DAILY_MAX', MAX_HOUR_DAY))
	weekly_cap = float(os.environ.get('WEEKLY_MAX', 37.5))

	for day in _working_days:
		# normalize existing values
		_df[day] = _df[day].apply(lambda x: float(str(x).replace(',', '.')) if x != '' else 0.0)
		_df[day] = _df[day].astype(float).fillna(0)

		# total currently assigned this day (from CSV)
		total_current = _df[day].sum()
		available = max(0.0, daily_cap - total_current)

		# collect per-activity needs (per-day minimums minus existing)
		needs = []
		for activity_key, activity_code in activities.items():
			if activity_key in _other_activities:
				value = _other_activities[activity_key]
				if value != -1:
					# existing hours for this activity on this day
					existing = _df.loc[_df['Id Actividad'] == activity_code, day].sum()
					need = max(0.0, float(value) - existing)
					needs.append((activity_key, activity_code, need))

		# allocate needs in deterministic order (teaching first etc.) without exceeding available
		for activity_key, activity_code, need in needs:
			if available <= 0:
				break
			alloc = min(need, available)
			if alloc > 0:
				# add allocation to the activity row(s) for that day
				_df.loc[_df['Id Actividad'] == activity_code, day] = _df.loc[_df['Id Actividad'] == activity_code, day] + alloc
				available -= alloc

		# after allocations, compute used hours for the day
		used_hours += _df[day].sum()

	max_hours_month = daily_cap * _num_working_days - used_hours
	# remaining capacity for project assignment should be non-negative
	if max_hours_month < 0:
		max_hours_month = 0

	if sum([x for x in _hours_by_project.values() if x != -1]) > max_hours_month:
		total_teaching_hours = _df.loc[_df['Id Actividad'] == 97, _df.columns[7:]].sum(axis=1).sum()
		total_other_id_hours = _df.loc[_df['Id Actividad'] == 98, _df.columns[7:]].sum(axis=1).sum()
		total_other_hours = _df.loc[_df['Id Actividad'] == 100, _df.columns[7:]].sum(axis=1).sum()
		total_lessons_hours = _df.loc[_df['Id Actividad'] == 108, _df.columns[7:]].sum(axis=1).sum()
		msg = f"Te has pasado de horas.\nEl máximo es de {MAX_HOUR_DAY}h al día y {MAX_HOUR_DAY * _num_working_days} horas este mes.\n"
		if total_teaching_hours > 0:
			msg += f"Has asignado {total_teaching_hours} horas de docencia\n"
		if total_other_id_hours > 0:
			msg += f"Has asignado {total_other_id_hours} horas de otras actividades de I+D\n"
		if total_other_hours > 0:
			msg += f"Has asignado {total_other_hours} horas de otras actividades\n"
		if total_lessons_hours > 0:
			msg += f"Has asignado {total_lessons_hours} horas de formación del participante\n"
		raise SolverException(msg)

	# daily check
	for day in _working_days:
		day_total = _df[day].sum()
		if day_total > daily_cap + 1e-6:
			raise SolverException(f"Se han asignado {day_total}h el día {day}, que supera el máximo diario de {daily_cap}h.")

	# weekly check: group by ISO year-week
	from dateutil import parser as _parser
	week_sums = {}
	for day in _working_days:
		dt = _parser.parse(day, dayfirst=True)
		yw = (dt.isocalendar().year, dt.isocalendar().week)
		week_sums.setdefault(yw, 0.0)
		week_sums[yw] += _df[day].sum()

	for yw, s in week_sums.items():
		if s > weekly_cap + 1e-6:
			raise SolverException(f"Semana {yw[0]}-W{yw[1]} tiene {s}h asignadas, que supera el máximo semanal de {weekly_cap}h.")

	return _df


if __name__ == '__main__':
	# CSV data in memory
	csv_data = """DNI;Nombre;Clave espec�fica;Proyecto;Id Actividad;Actividad;Working Package;1/2/23;2/2/23;3/2/23;4/2/23;5/2/23;6/2/23;7/2/23;8/2/23;9/2/23;10/2/23;11/2/23;12/2/23;13/2/23;14/2/23;15/2/23;16/2/23;17/2/23;18/2/23;19/2/23;20/2/23;21/2/23;22/2/23;23/2/23;24/2/23;25/2/23;26/2/23;27/2/23;28/2/23
33466494;PALANCA CAMARA, JAVIER;20221598;RECICLAI360;92;I+D+i ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;20221575;CITCOM.AI;92;I+D+i ;3;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;20220862;COSASS;92;I+D+i ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;-1;Otras Actividades;97;Docencia ;-1;;;;;;;;3;;;;;;;3;;;;;;;3;;;;;;
33466494;PALANCA CAMARA, JAVIER;-1;Otras Actividades;98;Otros proyectos I+D ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;-1;Otras Actividades;99;Ausencias/Vacaciones ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;-1;Otras Actividades;100;Otras actividades ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;
33466494;PALANCA CAMARA, JAVIER;-1;Otras Actividades;108;Formaci�n participante ;-1;;;;;;;;;;;;;;;;;;;;;;;;;;;;"""
	
	file_like = io.StringIO(csv_data)
	df, working_days, num_working_days = read_df(file_like)

	hours_by_project = {}

	hours_by_project, other_activities = cli_questions(df, hours_by_project)

	df = check_hours(df, working_days, num_working_days, other_activities, hours_by_project)

	# respect daily cap from environment if set
	try:
		daily_cap = float(os.environ.get('DAILY_MAX', MAX_HOUR_DAY))
	except Exception:
		daily_cap = MAX_HOUR_DAY
	df = solve_hours(df, hours_by_project, working_days, daily_max=daily_cap)

	df = transform_df_to_str_types(df, working_days)

	# Output to memory
	output = io.StringIO()
	df.to_csv(output, index=False, sep=";", encoding='iso-8859-1')
	print("Output CSV:")
	print(output.getvalue())
