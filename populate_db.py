import sys
import os
from pathlib import Path

# Set up paths so we can import database and models
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.append(str(backend_dir))

from database import init_db, save_incident
import sqlite3

def clean_and_populate_db():
    db_path = "data/incidents.db"
    
    # 1. Reset database if it exists
    print(f"Resetting database at {db_path}...")
    for suffix in ["", "-wal", "-shm"]:
        p = db_path + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
                
    init_db(db_path)
    
    # 2. Define diverse sample incidents
    sample_incidents = [
        {
            "source": "auth.log",
            "raw_line": "2026-07-02 12:00:00 CRITICAL auth: Brute force attempt detected: 150 failed login attempts in 1 minute from IP 198.51.100.42",
            "structured_log": {
                "timestamp": "2026-07-02 12:00:00",
                "severity": "CRITICAL",
                "module": "auth",
                "message": "Brute force attempt detected: 150 failed login attempts in 1 minute from IP 198.51.100.42"
            },
            "detection": {
                "is_incident": True,
                "severity": "CRITICAL"
            },
            "triage": {
                "category": "Security",
                "priority": "P0"
            },
            "resolution": {
                "status": "pending",
                "playbook_used": [
                    "Block the offending IP via firewall rules.",
                    "Audit authorization logs for any successful logins from this IP range.",
                    "Trigger password resets for targets of brute-force attempts.",
                    "Verify Intrusion Prevention System (IPS) rules."
                ],
                "steps_executed": [],
                "recommendation": "### Security Remediation Runbook\n\n1. **IP Blocking**:\n   Immediately run the firewall block script:\n   ```bash\n   sudo iptables -A INPUT -s 198.51.100.42 -j DROP\n   ```\n2. **Log Audit**:\n   Check if any auth attempts succeeded:\n   ```bash\n   grep '198.51.100.42' /var/log/auth.log | grep 'Accepted'\n   ```\n3. **Alerting**:\n   Notify the Security Operations Center (SOC) of the ongoing threat."
            },
            "notification": "CRITICAL: Security brute-force attack from IP 198.51.100.42"
        },
        {
            "source": "syslog",
            "raw_line": "2026-07-02 12:05:00 ERROR systemd: Out of Memory (OOM) killer invoked. Killed process 14201 (mysqld)",
            "structured_log": {
                "timestamp": "2026-07-02 12:05:00",
                "severity": "ERROR",
                "module": "systemd",
                "message": "Out of Memory (OOM) killer invoked. Killed process 14201 (mysqld)"
            },
            "detection": {
                "is_incident": True,
                "severity": "ERROR"
            },
            "triage": {
                "category": "Compute",
                "priority": "P1"
            },
            "resolution": {
                "status": "pending",
                "playbook_used": [
                    "Inspect system syslog for memory depletion indicators.",
                    "Reduce memory-intensive cache configurations (e.g. MySQL innodb_buffer_pool_size).",
                    "Restart the database service.",
                    "Verify memory usage is stable."
                ],
                "steps_executed": [
                    "Inspect system syslog for memory depletion indicators."
                ],
                "recommendation": "### Compute Memory Outage Runbook\n\n1. **MySQL Re-config**:\n   Adjust InnoDB cache limits in `/etc/mysql/my.cnf` to leave 20% system overhead.\n2. **Restart DB**:\n   ```bash\n   sudo systemctl restart mysql\n   ```\n3. **Monitor Memory Usage**:\n   Monitor via top or free command:\n   ```bash\n   free -m -s 5\n   ```"
            },
            "notification": "ERROR: MySQL killed by system Out-of-Memory (OOM)"
        },
        {
            "source": "disk_monitor.log",
            "raw_line": "2026-07-02 11:30:00 WARNING monitor: Storage utilization exceeded 95% on /var/log",
            "structured_log": {
                "timestamp": "2026-07-02 11:30:00",
                "severity": "WARNING",
                "module": "monitor",
                "message": "Storage utilization exceeded 95% on /var/log"
            },
            "detection": {
                "is_incident": True,
                "severity": "WARNING"
            },
            "triage": {
                "category": "Storage",
                "priority": "P2"
            },
            "resolution": {
                "status": "resolved",
                "playbook_used": [
                    "Find the largest directories using disk usage commands.",
                    "Locate and remove or compress old archived log files.",
                    "Trigger logrotate manually to free space.",
                    "Verify target disk space is below 80% threshold."
                ],
                "steps_executed": [
                    "Find the largest directories using disk usage commands.",
                    "Locate and remove or compress old archived log files.",
                    "Trigger logrotate manually to free space.",
                    "Verify target disk space is below 80% threshold."
                ],
                "recommendation": "### Storage Management Playbook\n\n1. **Analyze Space**:\n   ```bash\n   du -sh /var/log/* | sort -rh | head -10\n   ```\n2. **Clean Archives**:\n   Clean log zip archives older than 30 days:\n   ```bash\n   find /var/log -name '*.gz' -mtime +30 -exec rm {} \\;\n   ```"
            },
            "notification": "WARNING: Disk utilization critical on /var/log"
        },
        {
            "source": "gateway.log",
            "raw_line": "2026-07-02 11:15:00 ERROR gateway: Timeout (504 Gateway Timeout) connecting to external payment service api.stripe.com",
            "structured_log": {
                "timestamp": "2026-07-02 11:15:00",
                "severity": "ERROR",
                "module": "gateway",
                "message": "Timeout (504 Gateway Timeout) connecting to external payment service api.stripe.com"
            },
            "detection": {
                "is_incident": True,
                "severity": "ERROR"
            },
            "triage": {
                "category": "Network",
                "priority": "P3"
            },
            "resolution": {
                "status": "pending",
                "playbook_used": [
                    "Verify local server internet connectivity.",
                    "Check external API status page (Stripe Status).",
                    "Check server DNS configuration.",
                    "Check transit routing or firewall rules."
                ],
                "steps_executed": [],
                "recommendation": "### Network Latency Runbook\n\n1. **Check Connectivity**:\n   Ping target or execute a curl test:\n   ```bash\n   curl -I https://api.stripe.com/healthcheck\n   ```\n2. **Validate DNS resolution**:\n   ```bash\n   dig api.stripe.com\n   ```"
            },
            "notification": "ERROR: Gateway Timeout connecting to Stripe API"
        },
        {
            "source": "app.log",
            "raw_line": "2026-07-02 10:00:00 WARNING app: DeprecationWarning: imp module is deprecated. Use importlib instead",
            "structured_log": {
                "timestamp": "2026-07-02 10:00:00",
                "severity": "WARNING",
                "module": "app",
                "message": "DeprecationWarning: imp module is deprecated. Use importlib instead"
            },
            "detection": {
                "is_incident": True,
                "severity": "WARNING"
            },
            "triage": {
                "category": "Application",
                "priority": "P4"
            },
            "resolution": {
                "status": "resolved",
                "playbook_used": [
                    "Locate instances of imp imports in the codebase.",
                    "Replace deprecated imports with importlib module equivalent.",
                    "Run system test suites to verify functionality."
                ],
                "steps_executed": [
                    "Locate instances of imp imports in the codebase.",
                    "Replace deprecated imports with importlib module equivalent.",
                    "Run system test suites to verify functionality."
                ],
                "recommendation": "### Code Update recommendation\n\nIdentify references to `import imp` and replace with Python's standard `import importlib` package to maintain compatibility with modern Python environments."
            },
            "notification": "WARNING: Deprecations detected in application startup"
        }
    ]
    
    # 3. Save each incident
    print("Populating database with sample data...")
    for inc in sample_incidents:
        saved = save_incident(inc, db_path)
        print(f" - Created Incident ID {saved['incident_id']} (Priority: {saved['triage']['priority']}, Category: {saved['triage']['category']}, Status: {saved['resolution']['status']})")
        
    print("\nDatabase successfully populated!")

if __name__ == "__main__":
    clean_and_populate_db()
