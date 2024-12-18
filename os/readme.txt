use nginx as reverse proxy to forward badminton.homeip.net:80 request to 127.0.0.1:5000
also forward badminton.homeip.net:443 ssl request to http:80
other requests are handled by nginx default
