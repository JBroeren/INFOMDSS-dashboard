FROM jupyter/scipy-notebook
RUN pip install psycopg2-binary sqlalchemy pulp country_converter python-gnupg
USER root
RUN apt-get update && apt-get install -y gnupg