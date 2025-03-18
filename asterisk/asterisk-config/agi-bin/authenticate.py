#!/usr/bin/env python3
import sys
import requests
import logging
from asterisk.agi import AGI

logging.basicConfig(
    filename='/var/log/asterisk/authenticate.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('authenticate_agi')

def main():
    agi = AGI()
    agi.verbose("Starting authentication process")
    
    args = sys.argv[1:]
    if len(args) < 1:
        agi.verbose("Error: Missing PIN argument")
        agi.exec_command("Playback", "custom/system-error")
        sys.exit(1)
    
    pin = args[0]
    caller_id = args[1] if len(args) > 1 else "unknown"
    
    # Contact backend
    try:
        response = requests.post(
            "http://app:5000/authenticate",
            data={"pin": pin, "caller_id": caller_id},
            timeout=10
        )
        
        if response.status_code == 200 and response.json().get("status") == "success":
            agi.verbose(f"Authentication successful for caller ID: {caller_id}")
            agi.set_variable("AUTH_RESULT", "success")
            agi.exec_command("Goto", "auth_success,1")
        else:
            agi.verbose(f"Authentication failed for caller ID: {caller_id}")
            agi.set_variable("AUTH_RESULT", "failure")
            agi.exec_command("Goto", "auth_failure,1")
            
    except Exception as e:
        logger.error(f"Error during authentication: {str(e)}")
        agi.verbose(f"System error: {str(e)}")
        agi.exec_command("Playback", "custom/system-error")

if __name__ == "__main__":
    main()
