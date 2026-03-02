## Welcome
Welcome to my submission for the Agents League.
I did the 2nd track: Battle #2 - Reasoning Agents with Microsoft Foundry.

## Installation
The screenshots can be found in the folder 'alex-szarka-screenshots'.

Since the agents are hosted on Microsoft Foundry their yaml files can be found in
the 'alex-szarka-yaml' folder.

Steps to install:
* To install the app - load the agents into Microsoft Foundry (new foundry).
* run 'uv sync'
* It uses python 3.13 & has a uv.lock file to ensure it installs the same everywhere. The pyproject.toml has the required python packages listed.
* This was originally written on my Debian RaspberryPi computer - then I moved to a 16 gb ram Win11 Pro VM on Azure.

## Steps to run:
* cd to alex-szarka folder
* uv venv
* If on linux run: source .venv/bin/activate
* If on Windows run: .venv\Scripts\activate
* az login
* python main.py
* Run in either PowerShell or Bash:
> Invoke-RestMethod -Uri http://localhost:8066/responses -Method POST -ContentType "application/json" -Body '{"input": "I want to learn Azure fundamentals"}'

> curl -X POST http://localhost:8066/responses -H "Content-Type: application/json" -d "{\"input\": \"I want to learn Azure fundamentals\"}"


## Thank you for reviewing my submission!

Thanks,
Alex Szarka
developeralex@gmail.com
https://www.linkedin.com/in/developeralex
###### > Feel free to send me a personalized connection request on LinkedIn :)

