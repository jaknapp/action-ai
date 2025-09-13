# Action Terminal

API access to create processes and run commands through a web interface.

## Running with Docker

### Quick Start
```bash
# Build and start the service
docker-compose up --build

# Or run with Docker directly
docker build -t action-terminal .
docker run -p 5001:5001 -v $(pwd)/workspace:/workspace action-terminal
```

### Workspace Directory
The service uses a workspace directory for file operations and command outputs. When running with Docker:

- A `workspace` directory will be mounted from your local machine to `/workspace` in the container
- All file operations and command outputs will be available in this directory
- The directory is automatically created when you first run the container

### Configuration

The service runs on port 5001 by default. You can modify the following in `docker-compose.yml`:

- Port mapping (default: 5001:5001)
- Workspace directory location
- Resource limits (CPU/memory)

### Development

To run the service in development mode with local changes:

```bash
# Run with hot-reload for development
docker-compose up --build
```

### Notes

- The container has full internet access for package installation and external communication
- All command outputs in the workspace directory are persisted on your local machine
- The service runs in a hermetic environment, isolated from your host system
- Resource limits can be adjusted in docker-compose.yml as needed

```bash
docker build -t action-terminal .
docker run -p 5001:5001 action-terminal
```


## Run on VM

### Test VM on Mac

Run this command

```
cat <<EOF > ~/tmp/limited-docker.yaml
vmType: vz
cpus: 2
memory: 2GiB
disk: 10GiB

images:
  - location: "https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-arm64.img"
    arch: "aarch64"

mountType: virtiofs
mounts: []

containerd:
  system: false
  user: false

provision:
  - mode: system
    script: |
      sudo apt update
      sudo apt install -y docker.io
      sudo systemctl enable docker --now

      USERNAME=\$(getent passwd 1000 | cut -d: -f1)
      sudo usermod -aG docker "\$USERNAME"
      echo 'newgrp docker' | sudo tee -a /home/\$USERNAME/.bashrc
EOF

limactl stop limited-docker 2>/dev/null; \
limactl delete limited-docker 2>/dev/null; \
limactl create --name=limited-docker --tty=false ~/tmp/limited-docker.yaml && \
limactl start limited-docker && \
limactl shell limited-docker -- sudo mkdir -p /sys/fs/cgroup/mygroup && \
limactl shell limited-docker -- sudo bash -c 'echo +cpu > /sys/fs/cgroup/mygroup/cgroup.subtree_control' && \
limactl shell limited-docker -- sudo bash -c 'echo 50000 > /sys/fs/cgroup/mygroup/cpu.max' && \
limactl shell limited-docker -- sudo mkdir /sys/fs/cgroup/mygroup/test1 && \
limactl shell limited-docker -- sudo mkdir /sys/fs/cgroup/mygroup/test2 && \
limactl shell limited-docker -- sudo bash -c 'echo 50 > /sys/fs/cgroup/mygroup/test1/cpu.weight' && \
limactl shell limited-docker -- sudo bash -c 'echo 150 > /sys/fs/cgroup/mygroup/test2/cpu.weight' && \
limactl shell limited-docker -- sudo mkdir -p /etc/docker && \
limactl shell limited-docker -- sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "exec-opts": ["native.cgroupdriver=cgroupfs"]
}
EOF

limactl shell limited-docker -- sudo systemctl restart docker && \
limactl shell limited-docker -- sudo docker info | grep -i 'cgroup driver' && \
limactl shell limited-docker -- sudo docker rm -f test1; \
limactl shell limited-docker -- \
  sudo docker run --platform linux/arm64 -d --name test1 \
    --cpus=2 \
    --memory=512m \
    --cgroup-parent=/mygroup/test1 \
    alpine \
    /bin/sh -c "apk add --no-cache stress-ng && stress-ng --cpu 2 --timeout 20s" && \
limactl shell limited-docker -- sudo docker rm -f test2; \
limactl shell limited-docker -- \
  sudo docker run --platform linux/arm64 -d --name test2 \
    --cpus=2 \
    --memory=512m \
    --cgroup-parent=/mygroup/test2 \
    alpine \
    /bin/sh -c "apk add --no-cache stress-ng && stress-ng --cpu 2 --timeout 20s" && \
limactl shell limited-docker -- \
  sudo docker inspect test1 --format='Status: {{.State.Status}}, ExitCode: {{.State.ExitCode}}, Error: {{.State.Error}}' && \
end=$((SECONDS+10)); while [ $SECONDS -lt $end ]; do limactl shell limited-docker -- sudo docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"; sleep 1; done; \
limactl shell limited-docker -- sudo docker logs test1
```

### Action Server

Run action server in docker in the VM under a cgroup

```
docker build -t action-server:dev . && docker save action-server:dev > action-server.tar && limactl shell limited-docker -- sudo docker load < /Users/johnknapp/workspace/action-terminal/action-server.tar && limactl shell limited-docker -- sudo docker run --rm -it \
  --name action-server-chat1 \
  --cgroup-parent=/mygroup/test1 \
-v /Users/johnknapp/workspace/action-terminal:/app:ro \
-e WORKDIR=/app \
-p 8081:5001 \
action-server:dev
```