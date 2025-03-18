# Dockerfile for Asterisk PBX
FROM debian:bullseye-slim

# Install Asterisk and Python dependencies
RUN apt-get update && apt-get install -y \
    asterisk \
    python3 \
    python3-pip \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for AGI script
RUN pip3 install --no-cache-dir requests pyst2

# Copy Asterisk configuration
COPY asterisk-config/extensions.conf /etc/asterisk/
COPY asterisk-config/sip.conf /etc/asterisk/
COPY asterisk-config/voicemail.conf /etc/asterisk/
COPY asterisk-config/agi-bin/authenticate.py /var/lib/asterisk/agi-bin/
COPY asterisk-config/cdr_pgsql.conf /etc/asterisk/cdr_pgsql.conf

# Copy AGI script
COPY asterisk-config/agi-bin/authenticate.py /var/lib/asterisk/agi-bin/
RUN chmod 755 /var/lib/asterisk/agi-bin/authenticate.py

# Copy custom sound files
COPY sounds/custom/ /var/lib/asterisk/sounds/custom/

# Expose Asterisk ports
EXPOSE 5060/udp 5060/tcp 10000-20000/udp

# Run Asterisk in the foreground
CMD ["asterisk", "-f"]

