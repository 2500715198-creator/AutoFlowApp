# AutoFlow

Built for the Nebius x NVIDIA Global AI Hackathon 2026 (Coding and Agentic Engineering track).

Describe a repetitive task in plain English and paste sample data. An agent built on
NVIDIA Nemotron (served by Nebius Token Factory) writes a Python script, runs it in a sandbox,
checks the output against your request, and fixes its own mistakes until it passes.

## How it works
1. Nemotron writes a script that reads `input.txt` and prints a result.
2. The script runs in an isolated temp folder with a 10 second limit.
3. If it crashes, the error goes back to the model to fix.
4. If it runs, a second Nemotron call checks the output against the request. A failed check goes back to the model too.
5. After up to 4 attempts you get the working script to download.

## Run locally
    python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    export NEBIUS_API_KEY=your_key                     # Windows: set NEBIUS_API_KEY=your_key
    python app.py                                      # open http://localhost:5000

Create the key in the Nebius Token Factory console. Model and base URL can be changed with
`NEBIUS_MODEL` and `NEBIUS_BASE_URL`.

## Deploy (for the hosted demo URL)
Push to GitHub, then create a web service on Render, Railway or Fly.io. Start command is in `Procfile`.
Set `NEBIUS_API_KEY` as a secret environment variable.

## Security note
`run_sandbox()` in `app.py` runs model-written code on your server. It uses a temp folder, a timeout
and a stripped environment, but it does not block the network or file access. Before sharing a public
link, replace that one function with a Nebius Token Factory Sandbox call (or run the app in a locked-down container).

## Project structure
    app.py              Flask server and the agent loop (write, run, check, fix)
    static/index.html   Web interface that streams the agent's progress
    requirements.txt    Python dependencies
    Procfile            Start command for Render, Railway and similar hosts
    .env.example        Environment variable template

## Stack
NVIDIA Nemotron on Nebius Token Factory (OpenAI-compatible API), Python, Flask, plain HTML and JavaScript.

## License
MIT
