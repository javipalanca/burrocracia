# Flask application
import copy
import os
import random
import string

from flask import Flask, render_template, request, redirect, flash, send_from_directory
from pretty_html_table import build_table
from werkzeug.utils import secure_filename

from main import read_df, generate_questions, solve_hours, check_hours, transform_df_to_str_types

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

            return render_template('config.html', questions=questions, period=period, filename=filename)


@app.route('/solve', methods=['GET', 'POST'])
def solve():
    if request.method == 'POST':
        # Get form data
        form_data = request.form
        # Get filename
        filename = form_data['filename']
        # Get hours by project
        hours_by_project = {}

        for key, value in form_data.items():
            if key not in ['filename', 'submit']:
                project = key.replace("(", "").replace(")", "").replace("'", "").replace('"', "")
                name, hours = project.split(",")
                project = (name, float(hours))
                if project[0] == "__teaching__":
                    teaching_hours = float(value)
                elif project[0] == "__empty__":
                    hours_by_project[project] = value
                else:
                    hours_by_project[project] = float(value)
        # Solve hours
        df, working_days, num_working_days = read_df(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Check hours
        try:
            checked_df = check_hours(df, working_days, num_working_days, teaching_hours, hours_by_project)
        except Exception as e:
            msgs = str(e).split("\n")
            return render_template('error.html', error=msgs)

        solved_df = solve_hours(checked_df, hours_by_project, working_days)

        float_df = copy.deepcopy(solved_df)

        solved_df = transform_df_to_str_types(solved_df, working_days)

        # Save to CSV with random name
        random_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        solved_df.to_csv(os.path.join("results", f'solved_{random_id}.csv'), index=False, sep=";", encoding='iso-8859-1')

        # Delete column from df
        float_df = float_df.drop(columns=['DNI', "Nombre", "Clave específica", "Id Actividad"])
        # sum row from 7th row to end
        #float_df['Horas Totales'] = float_df.iloc[3:].sum()
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


# run Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0')
