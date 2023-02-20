FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1
LABEL maintainer="Javi Palanca <jpalanca@dsic.upv.es>"

RUN apt-get update -y && apt-get install -y build-essential
#    apt-get install -y python-pip python-dev
# We copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt


CMD [ "make", "serve" ]
