import sys
import requests

def main():
    url = "http://localhost:8000/ingest"
    
    # Default CRITICAL log line
    default_log = "2026-07-22 11:20:00 CRITICAL auth: Brute force attempt detected: 150 failed login attempts in 1 minute from IP 198.51.100.42"
    
    log_line = sys.argv[1] if len(sys.argv) > 1 else default_log
    
    print(f"Triggering log ingestion: {log_line}")
    try:
        resp = requests.post(url, json={"source": "trigger.log", "raw_line": log_line})
        if resp.status_code == 200:
            data = resp.json()
            incident_id = data.get("incident_id")
            print(f"✔ Success! Created Incident ID: {incident_id}")
            print("\nTo watch the live resolution:")
            print("1. Keep the backend server running (on port 8000).")
            print("2. Run the frontend server (run 'npm run dev' in the 'frontend/' folder).")
            print("3. Open http://localhost:3000 in your browser.")
            print(f"4. Click on INC-{incident_id} in the list and watch the flowchart map light up and the agent logs stream in real-time!")
        else:
            print(f"✘ Error: Server returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Connection Error: {e}")
        print("Please verify the backend server is running on http://localhost:8000.")

if __name__ == "__main__":
    main()
