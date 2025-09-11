INFOMDDS - Dashboard

This folder holds the barebone example dashboard template. This also provides a jupyter notebook to work on while learning various topics in the practical exercises and classrooms. You do not necessarily have to use this template but provides only a barebone structure in docker if you are looking for inspiration.

The folder contains several files and subfolders:

- /data > Holds data files you fetch or create.
- /notebook > Holds an example project that shows how you can use docker and the set up database to store and fetch data.
    --> You may also use this folder to create new notebooks to set up and test your data processing pipeline before integrating this in your flask app.
    - Dockerfile_notebook > Dockerfile for the Jupyter notebooks.
- /dashboard > This is a Flask application that you may use to host your dashboard using localhost.
    - /static > Holds your css and images for the dashboard etc.
    - /templates > Holds your HTML templates you can use, especially useful if you will be using multiple pages in your dashboard.
    - /src > Empty folder to hold your additional methods and helper functions (think about processing data and generating charts)
    - app.py > This is the main Flask app that hosts your dashboard.
    - Dockerfile_dashboard > Dockerfile for the flask-app.
    - requirements.txt > Holds all python libraries that you use, remember to update this file!
- docker-compose.yml > Is used to set up the environments and docker containers.

In this project, a real-world example is presented with data retrieved from The United Nations (https://population.un.org/wpp/Download/). A sample is taken from a dataset on world population growth. The sample is saved in the /data folder under 'world_population.csv'. The data is used to populate the database and create interactive graphs as an example.

Remember that this setup is an example. You may use any other framework that you are (more) familiar with like Vue, Angular etc.

How do I use this barebone project? (Assuming you have Docker and the Docker engine installed)
- Open a terminal or command prompt
- CD to this directory called 'INFOMDSS_Dashboard'
- run 'docker compose up'. In some versions, you might need docker-compose up
- You can also use docker-compose up -d for running in daemon mode (hidden)
- Running this command for the first time might take a few minutes
- Jupyter notebook is available at localhost:8888 and dashboard at localhost:8080