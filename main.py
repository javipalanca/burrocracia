import calendar
import random

import pandas as pd
from tabulate import tabulate


def get_working_days(month, year):
    """Returns a list of the working days in a month"""
    working_days = []
    for day in calendar.Calendar().itermonthdates(year, month):
        if day.month == month and day.weekday() < 5:
            working_days.append(day.strftime("%-d/%-m/%y"))
    return working_days


MAX_HOUR_DAY = 7.5

if __name__ == '__main__':
    # load csv to dataframe with iso-8859-1 encoding
    filename = "/Users/jpalanca/Downloads/Horas_Participante (1).csv"
    df = pd.read_csv(filename, encoding='iso-8859-1', sep=';')

    # get name of the 8th column
    name = df.columns[7]
    _, month, year = name.split('/')
    month = int(month)
    year = int(year)

    hours_by_project = {}

    for index, row in df.iterrows():
        if row["Id Actividad"] == 92:
            project = row["Proyecto"]
            wp = int(row["Working Package"])
            if wp != -1:
                hours = input(f"Cuantas horas deseas imputar al WP {wp} del proyecto {project} (-1 si no hay mínimo): ")
                hours_by_project[project, wp] = int(hours)
            else:
                hours = input(f"Cuantas horas deseas imputar al proyecto {project} (-1 si no hay mínimo): ")
                hours_by_project[project, -1] = int(hours)

    working_days = get_working_days(month, year)
    num_working_days = len(working_days)

    used_hours = 0
    # set df columns to float type with default value 0
    for day in working_days:
        df[day] = df[day].apply(lambda x: float(str(x).replace(',', '.')))
        df[day] = df[day].astype(float).fillna(0)

        used_hours += df[day].sum()

    max_hours_month = MAX_HOUR_DAY * num_working_days -used_hours

    if sum([x for x in hours_by_project.values() if x != -1]) > max_hours_month:
        print(f"Te has pasado de horas. El máximo es de 7.5h al día y {max_hours_month} horas este mes")
        exit(1)



    # iter dataframe by rows
    for index, row in df.iterrows():
        project, wp = row['Proyecto'], row['Working Package']
        if (project, wp) not in hours_by_project:
            continue
        if hours_by_project[(project, wp)] == -1:
            continue
        while hours_by_project[(project, wp)] > 0:
            for day in working_days:
                pending_hours_in_day = MAX_HOUR_DAY - df[day].sum()
                new_hours = min(min(1, hours_by_project[(project, wp)]), pending_hours_in_day)
                # update dataframe
                df.loc[index, day] = df.loc[index, day] + new_hours
                hours_by_project[(project, wp)] -= new_hours

    # projects without min hours restriction
    projects_without_restriction = [key for key, value in hours_by_project.items() if value == -1]

    for day in working_days:
        project = random.choice(projects_without_restriction)
        pending_hours_in_day = MAX_HOUR_DAY - df[day].sum()
        # locate by two columns and row in df
        df.loc[(df['Proyecto'] == project[0]) & (df['Working Package'] == project[1]), day] = pending_hours_in_day
        df[day] = df[day].apply(lambda x: str(x).replace('.', ',') if x != 0.0 else '')

    df.to_csv('/Users/jpalanca/Downloads/output.csv', index=False, sep=";", encoding='iso-8859-1')
