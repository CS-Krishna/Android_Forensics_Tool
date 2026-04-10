# Android Digital Forensics Tool



A web-based Android forensic artefact collection and analysis tool built as part of an M.Sc. Digital Forensics and Information Security project at NFSU Goa Campus.



## Features



- **Evidence Ingestion** \- supports `.zip`, `.tar`, `.gz`, and extracted folders

- **ALEAPP Integration** \- automatic Android artefact parsing

- **SMS / MMS Search** \- full-text search across message artefacts

- **YOLOv8 Image Analysis** \- dual-model detection (general COCO-80 + custom weapon detector)

- **Case Management** \- multiple isolated cases with create, rename, delete, and switch support

- **HTML Report Export** \- fully self-contained forensic report with dark/light theme toggle



## Setup



### Prerequisites

- Python 3.11

- Git

- ADB (Android Debug Bridge)

- Visual C++ Build Tools (Windows)



### Installation



```bash

# Clone the repository

git clone https://github.com/CS-Krishna/Android_Forensics_Tool.git

cd Android_Forensics_Tool



# Create and activate virtual environment

python -m venv venv

venvScriptsactivate   # Windows

source venv/bin/activate # Linux/Mac



# Install dependencies

pip install -r requirements.txt



# Clone ALEAPP

git clone https://github.com/abrignoni/ALEAPP.git

pip install -r ALEAPP/requirements.txt



# Add your YOLOv8 weapon model

# Place best.pt in the project root directory

```



### Running



```bash

python app.py

```



Open http://127.0.0.1:5000 in your browser.



## Usage



1. Create a new case from the dashboard

2. Ingest evidence (zip/tar/folder from ADB pull, FTK Imager, or Oxygen Forensic export)

3. Run image analysis

4. Browse artefacts, search SMS/MMS, view image detections

5. Export HTML report



## Tech Stack



- **Flask** \- web framework

- **ALEAPP** \- Android artefact parser

- **YOLOv8 (Ultralytics)** \- object detection

- **OpenCV / Pillow** \- image processing

- **Pandas / OpenPyXL** \- data handling



## Disclaimer



This tool is intended for lawful forensic investigation purposes only.

