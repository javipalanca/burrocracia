# Flask application
import copy
import os
import random
import string
import re

from flask import Flask, render_template, request, redirect, flash, send_from_directory, jsonify
from pretty_html_table import build_table
from werkzeug.utils import secure_filename

from main import read_df, generate_questions, solve_hours, check_hours, transform_df_to_str_types, SolverException

app = Flask(__name__)

# Set UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = 'uploads'
# Set template folder
app.config['TEMPLATES_AUTO_RELOAD'] = True

ALLOWED_EXTENSIONS = {'csv'}


def allowed_file(filename):
	return '.' in filename and \
		filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# View to ask for CSV file
@app.route('/', methods=['GET'])
def index():
	return render_template('index.html')


@app.route('/config', methods=['GET', 'POST'])
def config():
	if request.method == 'POST':
		# check if the post request has the file part
		if 'file' not in request.files:
			flash('No file part')
			return redirect(request.url)
		file = request.files['file']
		if file.filename == '':
			flash('No selected file')
			return redirect(request.url)
		if file and allowed_file(file.filename):
			filename = secure_filename(file.filename)
			file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

			df, working_days, num_working_days = read_df(os.path.join(app.config['UPLOAD_FOLDER'], filename))
			questions = generate_questions(df)
			period = working_days[0] + ' - ' + working_days[-1]
			max_hours_month = 7.5 * len(working_days)

			# compute existing assigned hours (from CSV)
			activities_codes = {"__teaching__": 97, "__other_id__": 98, "__other__": 100, "__lessons__": 108}
			# normalize working_days columns to numeric (replace commas, empty strings)
			_num_df = df[working_days].replace('', 0).applymap(lambda x: float(str(x).replace(',', '.')) if x not in [None, ''] else 0.0)
			existing_by_activity = {}
			for k, code in activities_codes.items():
				# select rows for activity, convert those columns to numeric similarly
				sel = df.loc[df['Id Actividad'] == code, working_days]
				if sel.shape[0] == 0:
					existing_by_activity[k] = 0.0
				else:
					sel_num = sel.replace('', 0).applymap(lambda x: float(str(x).replace(',', '.')) if x not in [None, ''] else 0.0)
					existing_by_activity[k] = float(sel_num.sum(axis=1).sum())

			existing_total = float(_num_df.sum(axis=1).sum())

			return render_template('config.html', questions=questions, period=period, filename=filename,
								   num_working_days=len(working_days), max_hours_month=max_hours_month,
								   existing_total=existing_total, existing_by_activity=existing_by_activity)


@app.route('/solve', methods=['GET', 'POST'])
def solve():
	if request.method == 'POST':
		# Get form data
		form_data = request.form
		# Get filename
		filename = form_data['filename']
		# Get hours by project
		hours_by_project = {}
		other = {}

		for key, value in form_data.items():
			if key not in ['filename', 'submit']:
				# parse key robustly: expect something like "('Project Name, possibly with commas', -1)"
				s = key.strip()
				if s.startswith('(') and s.endswith(')'):
					s = s[1:-1]
				# try regex to capture last comma + integer (wp)
				m = re.match(r'^(.*),\s*(-?\d+)\s*$', s)
				if m:
					name_part = m.group(1).strip()
					hours_part = m.group(2).strip()
				else:
					parts = s.rsplit(',', 1)
					name_part = parts[0].strip()
					hours_part = parts[1].strip() if len(parts) > 1 else '-1'
				# strip surrounding quotes from name
				name_part = name_part.strip().strip('"\'')
				try:
					wp = int(hours_part)
				except Exception:
					wp = int(float(hours_part))
				project = (name_part, wp)
				# debug log (prints to server console)
				print('Parsed form key ->', project, 'value=', value)
				if project[0] in ["__teaching__", "__other_id__", "__other__", "__lessons__"]:
					other[project[0]] = float(value) if value != "" else 0
				elif project[0] == "__empty__":
					hours_by_project[project] = value
				else:
					hours_by_project[project] = float(value) if value != "" else 0
		# Solve hours
		df, working_days, num_working_days = read_df(os.path.join(app.config['UPLOAD_FOLDER'], filename))

		# Check hours
		try:
			checked_df = check_hours(df, working_days, num_working_days, other, hours_by_project)
		except SolverException as e:
			msgs = str(e).split("\n")
			return render_template('error.html', error=msgs)

		# use daily cap from env if set
		try:
			daily_cap = float(os.environ.get('DAILY_MAX', 7.5))
		except Exception:
			daily_cap = 7.5
		solved_df = solve_hours(checked_df, hours_by_project, working_days, daily_max=daily_cap)

		float_df = copy.deepcopy(solved_df)

		solved_df = transform_df_to_str_types(solved_df, working_days)

		# Save to CSV with random name
		random_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
		solved_df.to_csv(os.path.join("results", f'solved_{random_id}.csv'), index=False, sep=";", encoding='iso-8859-1')

		# Delete column from df
		float_df = float_df.drop(columns=['DNI', "Nombre", "Clave específica", "Id Actividad"])
		# sum row from 7th row to end
		# float_df['Horas Totales'] = float_df.iloc[3:].sum()
		float_df['Horas Totales'] = float_df.loc[:, float_df.columns[3:]].sum(axis=1)
		# reorder column
		columns = ["Proyecto", "Actividad", "Working Package", "Horas Totales"]
		float_df = float_df[columns + [col for col in float_df.columns if col not in columns]]
		# Build table
		html_table = build_table(float_df, 'blue_light')

		return render_template('result.html', df=html_table, random_id=random_id)


@app.route('/download/<random_id>', methods=['GET'])
def download(random_id):
	# return file download
	return send_from_directory("results", f'solved_{random_id}.csv', as_attachment=True)


@app.route('/preview', methods=['POST'])
def preview():
	# Accept same form as /solve and return JSON with per-row totals and totals
	form_data = request.form
	filename = form_data.get('filename')
	if not filename:
		return jsonify({'error': 'filename missing'}), 400

	# parse form into hours_by_project and other
	hours_by_project = {}
	other = {}
	for key, value in form_data.items():
		if key not in ['filename', 'submit']:
			s = key.strip()
			if s.startswith('(') and s.endswith(')'):
				s = s[1:-1]
			m = re.match(r'^(.*),\s*(-?\d+)\s*$', s)
			if m:
				name_part = m.group(1).strip()
				hours_part = m.group(2).strip()
			else:
				parts = s.rsplit(',', 1)
				name_part = parts[0].strip()
				hours_part = parts[1].strip() if len(parts) > 1 else '-1'
			name_part = name_part.strip().strip('"\'')
			try:
				wp = int(hours_part)
			except Exception:
				wp = int(float(hours_part))
			project = (name_part, wp)
			if project[0] in ["__teaching__", "__other_id__", "__other__", "__lessons__"]:
				other[project[0]] = float(value) if value != "" else 0
			elif project[0] == "__empty__":
				hours_by_project[project] = value
			else:
				hours_by_project[project] = float(value) if value != "" else 0

	# read df and compute solved allocation
	try:
		df, working_days, num_working_days = read_df(os.path.join(app.config['UPLOAD_FOLDER'], filename))
	except Exception as e:
		return jsonify({'error': f'Error reading CSV: {e}'}), 400

	try:
		checked_df = check_hours(df.copy(), working_days, num_working_days, other, hours_by_project)
	except SolverException as e:
		return jsonify({'error': str(e)}), 400

	try:
		daily_cap = float(os.environ.get('DAILY_MAX', 7.5))
	except Exception:
		daily_cap = 7.5
	solved_df = solve_hours(checked_df.copy(), hours_by_project, working_days, daily_max=daily_cap)

	# build the same summary table as /solve: drop identifying cols, compute 'Horas Totales' per row
	float_df = copy.deepcopy(solved_df)
	# drop columns if present
	for colname in ['DNI', 'Nombre', 'Clave específica', 'Id Actividad']:
		if colname in float_df.columns:
			float_df = float_df.drop(columns=[colname])
	# sum from 4th column onward (index 3)
	float_df['Horas Totales'] = float_df.loc[:, float_df.columns[3:]].replace('', 0).applymap(lambda x: float(str(x).replace(',', '.')) if x not in [None, ''] else 0.0).sum(axis=1)
	# reorder columns to put Proyecto, Actividad, Working Package, Horas Totales first if they exist
	columns = [c for c in ["Proyecto", "Actividad", "Working Package", "Horas Totales"] if c in float_df.columns]
	float_df = float_df[columns + [col for col in float_df.columns if col not in columns]]

	rows = []
	# mapping for activity codes (fallback)
	activity_names = {97: 'Docencia', 98: 'Otros proyectos I+D', 99: 'Ausencias/Vacaciones', 100: 'Otras actividades', 108: 'Formación participante'}
	for index, row in float_df.iterrows():
		proj = row.get('Proyecto')
		actividad = ''
		idcode = None
		# prefer explicit 'Actividad' label only for display; but only replace project name
		# when the row corresponds to a known activity code
		if 'Actividad' in row.index and str(row.get('Actividad')).strip() != '':
			actividad = row.get('Actividad')

		# try to read Id Actividad from solved_df to detect special activity rows
		try:
			idcode = int(solved_df.loc[index, 'Id Actividad'])
		except Exception:
			idcode = None

		# if idcode maps to a known activity, use that as project name and actividad
		if idcode in activity_names:
			actividad = activity_names.get(idcode, '')
			proj = actividad

		wp = int(row.get('Working Package')) if 'Working Package' in row.index else -1
		hours_total = float(row['Horas Totales']) if 'Horas Totales' in row.index else 0.0

		rows.append({'project': proj, 'actividad': actividad, 'wp': wp, 'hours': hours_total})

	assigned_total = float(float_df['Horas Totales'].sum()) if 'Horas Totales' in float_df.columns else 0.0
	max_hours = 7.5 * len(working_days)
	remaining = max_hours - assigned_total

	return jsonify({'rows': rows, 'assigned_total': assigned_total, 'remaining': remaining})


# run Flask app
if __name__ == '__main__':
	# Use localhost by default and a safe port; allow override via PORT/HOST env vars
	host = os.environ.get('HOST', '127.0.0.1')
	try:
		port = int(os.environ.get('PORT', '8000'))
	except ValueError:
		port = 8000
	app.run(host=host, port=port, debug=True)
