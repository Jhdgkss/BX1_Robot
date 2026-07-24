$body = @{
    robot_id = "BX1"
    message = "Hello from the API test. Who are you?"
    body_state = @{
        battery = 78
        pitch_deg = 0.2
        roll_deg = -0.1
        location = "workshop"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/chat" -Method Post -ContentType "application/json" -Body $body
