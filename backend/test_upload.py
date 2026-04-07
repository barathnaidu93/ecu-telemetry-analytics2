import requests
import glob
for f in glob.glob("../csv_logs/*.csv") + glob.glob("../*.csv"):
    with open(f, 'rb') as fp:
        try:
            r = requests.post("http://localhost:8889/upload", files={"file": fp})
            if r.status_code != 200:
                print(f"Failed {f}: {r.text}")
        except Exception as e:
            print(f"Exception on {f}: {e}")
