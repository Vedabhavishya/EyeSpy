import requests
import threading
import time

def read_stream():
    try:
        print("Starting stream read...")
        r = requests.get("http://127.0.0.1:5000/detect-drowsy", stream=True, timeout=5)
        for chunk in r.iter_content(chunk_size=1024):
            # Just read a bit of the stream
            pass
    except Exception as e:
        print("Stream read ended/failed:", e)

def poll_stats():
    time.sleep(1)
    try:
        print("Polling stats API...")
        start = time.time()
        r = requests.get("http://127.0.0.1:5000/api/live-stats", timeout=3)
        print(f"Stats response: {r.status_code}, content: {r.json()}, took {time.time() - start:.3f}s")
    except Exception as e:
        print("Stats poll failed:", e)

# We will only run this test if the server is running.
if __name__ == "__main__":
    t1 = threading.Thread(target=read_stream)
    t2 = threading.Thread(target=poll_stats)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
