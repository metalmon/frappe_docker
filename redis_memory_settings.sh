#!/bin/bash

# Function to show usage
show_usage() {
    echo "Usage: $0 [enable|disable|status]"
    echo "  enable  - Enable Redis memory overcommit"
    echo "  disable - Disable Redis memory overcommit"
    echo "  status  - Show current memory overcommit status"
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
    local current_value
    current_value=$(sysctl vm.overcommit_memory | awk '{print $3}')
    echo "Current memory overcommit setting: $current_value"
    case $current_value in
        0) echo "Memory overcommit is DISABLED (default)" ;;
        1) echo "Memory overcommit is ENABLED (Redis recommended)" ;;
        2) echo "Memory overcommit is set to STRICT mode" ;;
    esac
}

# Function to enable memory overcommit
enable_overcommit() {
    check_root
    echo "Enabling memory overcommit..."
    
    # Set immediate effect
    sysctl -w vm.overcommit_memory=1
    
    # Make it permanent
    if ! grep -q "vm.overcommit_memory = 1" /etc/sysctl.conf; then
        echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf
        echo "Added permanent setting to /etc/sysctl.conf"
    else
        echo "Permanent setting already exists in /etc/sysctl.conf"
    fi
    
    echo "Memory overcommit has been enabled"
    get_status
}

# Function to disable memory overcommit
disable_overcommit() {
    check_root
    echo "Disabling memory overcommit..."
    
    # Set immediate effect
    sysctl -w vm.overcommit_memory=0
    
    # Remove from permanent configuration
    sed -i '/vm.overcommit_memory = 1/d' /etc/sysctl.conf
    echo "Removed permanent setting from /etc/sysctl.conf"
    
    echo "Memory overcommit has been disabled"
    get_status
}

# Main script
case "$1" in
    enable)
        enable_overcommit
        ;;
    disable)
        disable_overcommit
        ;;
    status)
        get_status
        ;;
    *)
        show_usage
        ;;
esac 