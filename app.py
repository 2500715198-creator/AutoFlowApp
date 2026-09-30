"""AutoFlow: describe a repetitive task, an agent writes, runs, checks and fixes the code.

Model calls go to NVIDIA Nemotron on Nebius Token Factory (OpenAI-compatible API).
"""
import json, os, re, subprocess, sys, tempfile, time
from flask import Flask, Response, request, send_from_directory

BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
MODEL = os.environ.get("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "4"))

app = Flask(__name__, static_folder="static")

WRITER = (
    "You write one Python 3 script using only the standard library. "
    "The script reads the file 'input.txt' in the current directory (sample data from the user, "
    "often CSV) and prints its result to stdout. Do not use the network. "
    "Reply with a single ```python code block and nothing else."
)
CHECKER = (
    "You check whether a script's output correctly does what the user asked, given the sample input. "
    'Reply with only JSON: {"pass": true or false, "reason": "one short sentence"}.'
)


def ask(messages):
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=os.environ["NEBIUS_API_KEY"])
    r = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2, max_tokens=6000)
    text = r.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def extract_code(text):
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return blocks[-1].strip() if blocks else ""


def run_sandbox(code, data):
    """Runs generated code in a temp dir with a timeout.
    For the hackathon, swap this one function for a Nebius Token Factory Sandbox call."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "solution.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(d, "input.txt"), "w", encoding="utf-8") as f:
            f.write(data)
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT")}
        try:
            p = subprocess.run([sys.executable, "-I", "solution.py"], cwd=d, capture_output=True,
                               text=True, timeout=10, env=env)
            return p.returncode, p.stdout[-3000:], p.stderr[-3000:]
        except subprocess.TimeoutExpired:
            return 124, "", "Timed out after 10 seconds"


def verify(task, data, code, out):
    text = ask([
        {"role": "system", "content": CHECKER},
        {"role": "user", "content": f"Task:\n{task}\n\nSample input:\n{data[:3000]}\n\nScript:\n{code}\n\nOutput:\n{out}"},
    ])
    m = re.search(r"\{.*\}", text, re.S)
    try:
        j = json.loads(m.group(0))
        return bool(j.get("pass")), str(j.get("reason", ""))
    except Exception:
        return False, "The checker gave an unreadable answer."


def agent(task, data):
    start = time.time()
    msgs = [{"role": "system", "content": WRITER},
            {"role": "user", "content": f"Task:\n{task}\n\nSample input (input.txt):\n{data[:3000]}"}]
    code = ""
    for n in range(1, MAX_ATTEMPTS + 1):
        yield {"type": "step", "text": f"Attempt {n}: writing code"}
        reply = ask(msgs)
        code = extract_code(reply)
        if not code:
            msgs += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "I could not find a python code block. Reply with one ```python block."}]
            yield {"type": "problem", "text": "The model did not return code. Retrying."}
            continue
        yield {"type": "code", "attempt": n, "code": code}
        yield {"type": "step", "text": "Running it in the sandbox"}
        rc, out, err = run_sandbox(code, data)
        if rc != 0:
            yield {"type": "problem", "text": err.strip().splitlines()[-1] if err.strip() else f"Exit code {rc}", "detail": err}
            feedback = f"The script failed with exit code {rc}.\nError:\n{err}\nFix the script and reply with the full corrected code."
        else:
            yield {"type": "output", "text": out}
            yield {"type": "step", "text": "Checking the output against your request"}
            ok, reason = verify(task, data, code, out)
            if ok:
                yield {"type": "done", "ok": True, "code": code, "attempts": n, "seconds": round(time.time() - start, 1), "reason": reason}
                return
            yield {"type": "problem", "text": reason}
            feedback = f"The script ran but the output is wrong: {reason}\nOutput was:\n{out}\nFix the script and reply with the full corrected code."
        msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": feedback}]
    yield {"type": "done", "ok": False, "code": code, "attempts": MAX_ATTEMPTS, "seconds": round(time.time() - start, 1),
           "reason": "Could not get a passing result. Try a clearer description or more sample data."}


@app.post("/api/build")
def build():
    body = request.get_json(silent=True) or {}
    task = str(body.get("task", ""))[:2000].strip()
    data = str(body.get("data", ""))[:20000]
    if not task:
        return {"error": "Describe the task first."}, 400
    if not os.environ.get("NEBIUS_API_KEY"):
        return {"error": "NEBIUS_API_KEY is not set on the server."}, 500

    def stream():
        try:
            for ev in agent(task, data):
                yield json.dumps(ev) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "text": f"Model call failed: {e}"}) + "\n"

    return Response(stream(), mimetype="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
