# DenarioApp

DenarioApp is the GUI for multiagent research assitant system [Denario](https://github.com/AstroPilot-AI/Denario.git), powered by [streamlit](https://streamlit.io).

[Test a deployed demo of this app in HugginFace Spaces.](https://huggingface.co/spaces/astropilot-ai/Denario)

<img width="1793" height="694" alt="Screenshot from 2025-09-10 18-30-46" src="https://github.com/user-attachments/assets/2c524601-13ff-492b-addb-173323aaa15b" />

## Launch the GUI

Install the app with

```bash
pip install "denario[app]"
```

or, if Denario is already installed, do:

```bash
pip install denario_app
```

Then, launch the app with

```bash
denario run
```

## Build the GUI from source

First, clone the app with

`git clone https://github.com/AstroPilot-AI/DenarioApp.git`

Install the GUI from source following one of the following steps:

1. Install with pip

   ```bash
   pip install -e .
   ```

2. Install with [uv](https://docs.astral.sh/uv/)

   ```bash
   uv sync
   ```

Run the app with:

```bash
denario run
```

or

```bash
streamlit run src/denario_app/app.py
```
