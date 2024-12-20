#!/bin/bash

# Function to show usage
show_usage() {
    echo "Usage: $0 [enable|disable|status]"
    echo "  enable  - Enable host optimizations"
    echo "  disable - Disable host optimizations"
    echo "  status  - Show current optimization status"
    exit 1
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Please run as root or with sudo"
        exit 1
    fi
}

# Function to get current status
get_status() {
    echo "=== Current System Settings ==="
    echo "Memory Management:"
    sysctl vm.overcommit_memory
    sysctl vm.swappiness
    
    echo -e "\nFile Descriptors:"
    ulimit -n
    
    echo -e "\nNetwork Settings:"
    sysctl net.core.somaxconn
    sysctl net.ipv4.tcp_max_syn_backlog
    sysctl net.ipv4.ip_local_port_range
    
    echo -e "\nI/O Settings:"
    cat /sys/block/$(mount | grep " / " | cut -d' ' -f1 | sed 's/[0-9]*$//g' | sed 's/\/dev\///g')/queue/scheduler
}

# Function to enable optimizations
enable_optimizations() {
    check_root
    echo "Enabling host optimizations for virtual server..."
    
    # Memory Management
    echo "Configuring memory management..."
    echo 'vm.overcommit_memory = 1' > /etc/sysctl.d/90-memory.conf
    echo 'vm.swappiness = 10' >> /etc/sysctl.d/90-memory.conf
    
    # File descriptor limits
    echo "Setting file descriptor limits..."
    if ! grep -q "* soft nofile" /etc/security/limits.conf; then
        echo "* soft nofile 32768" >> /etc/security/limits.conf
        echo "* hard nofile 32768" >> /etc/security/limits.conf
    fi
    
    # Network optimizations (conservative settings for virtual server)
    echo "Configuring network settings..."
    cat > /etc/sysctl.d/91-network.conf << EOF
# Max connection backlog
net.core.somaxconn = 2048
# TCP backlog
net.ipv4.tcp_max_syn_backlog = 2048
# Local port range
net.ipv4.ip_local_port_range = 10240 65535
# TCP keepalive
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3
# TCP memory usage (auto-tuned)
net.ipv4.tcp_moderate_rcvbuf = 1
EOF
    
    # I/O Scheduler optimization
    echo "Configuring I/O scheduler..."
    root_disk=$(mount | grep " / " | cut -d' ' -f1 | sed 's/[0-9]*$//g' | sed 's/\/dev\///g')
    if [ -f "/sys/block/$root_disk/queue/scheduler" ]; then
        echo "none" > "/sys/block/$root_disk/queue/scheduler"
    fi
    
    # Apply sysctl changes
    echo "Applying changes..."
    sysctl --system
    
    echo "Host optimizations have been enabled"
    echo "Note: Some changes may require a system reboot to take effect"
    get_status
}

# Function to disable optimizations
disable_optimizations() {
    check_root
    echo "Disabling host optimizations..."
    
    # Remove custom sysctl configurations
    rm -f /etc/sysctl.d/90-memory.conf
    rm -f /etc/sysctl.d/91-network.conf
    
    # Remove custom limits
    sed -i '/\* soft nofile/d' /etc/security/limits.conf
    sed -i '/\* hard nofile/d' /etc/security/limits.conf
    
    # Reset I/O scheduler to default (cfq or mq-deadline depending on the system)
    root_disk=$(mount | grep " / " | cut -d' ' -f1 | sed 's/[0-9]*$//g' | sed 's/\/dev\///g')
    if [ -f "/sys/block/$root_disk/queue/scheduler" ]; then
        echo "mq-deadline" > "/sys/block/$root_disk/queue/scheduler"
    fi
    
    # Apply default sysctl settings
    sysctl --system
    
    echo "Host optimizations have been disabled"
    echo "Note: Some changes may require a system reboot to take effect"
    get_status
}

# Main script
case "$1" in
    enable)
        enable_optimizations
        ;;
    disable)
        disable_optimizations
        ;;
    status)
        get_status
        ;;
    *)
        show_usage
        ;;
esac 