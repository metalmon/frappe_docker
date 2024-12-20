#!/bin/bash

# Function to show usage
show_usage() {
    echo "Usage: $0 [apply|remove|status|rebuild]"
    echo "  apply   - Apply container optimizations"
    echo "  remove  - Remove container optimizations"
    echo "  status  - Show current optimization status"
    echo "  rebuild - Rebuild and restart containers"
    exit 1
}

# Function to check if docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Docker is not installed. Please install Docker first."
        exit 1
    fi
}

# Function to check if docker-compose is installed
check_compose() {
    if ! command -v docker compose &> /dev/null; then
        echo "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Function to check if exp.yaml exists
check_config() {
    if [ ! -f "exp.yaml" ]; then
        echo "exp.yaml not found in current directory"
        exit 1
    fi
}

# Function to rebuild containers
rebuild_containers() {
    check_docker
    check_compose
    check_config
    echo "Rebuilding containers using exp.yaml configuration..."
    
    # Stop containers
    echo "Stopping containers..."
    docker compose --project-name exp -f exp.yaml down
    
    # Pull latest images
    echo "Pulling latest images..."
    docker compose --project-name exp -f exp.yaml pull
    
    # Start containers
    echo "Starting containers..."
    docker compose --project-name exp -f exp.yaml up -d
    
    # Wait for containers to be healthy
    echo "Waiting for containers to be ready..."
    sleep 10
    
    echo "Rebuild complete. Current container status:"
    docker compose --project-name exp -f exp.yaml ps
}

# Function to get current status
get_status() {
    check_config
    echo "=== Current Container Settings ==="
    
    echo -e "\nContainer Status:"
    docker compose --project-name exp -f exp.yaml ps
    
    echo -e "\nRedis Cache Settings:"
    docker exec -i exp-redis-cache-1 redis-cli CONFIG GET maxmemory 2>/dev/null || echo "Redis cache container not running"
    docker exec -i exp-redis-cache-1 redis-cli CONFIG GET maxmemory-policy 2>/dev/null || echo "Redis cache container not running"
    
    echo -e "\nRedis Queue Settings:"
    docker exec -i exp-redis-queue-1 redis-cli CONFIG GET maxmemory 2>/dev/null || echo "Redis queue container not running"
    docker exec -i exp-redis-queue-1 redis-cli CONFIG GET maxmemory-policy 2>/dev/null || echo "Redis queue container not running"
}

# Function to optimize Redis settings
optimize_redis() {
    local container=$1
    local maxmem=$2
    local policy=$3
    
    echo "Optimizing Redis container: $container"
    
    # Create Redis config with settings
    docker exec -i "$container" /bin/sh -c "echo 'maxmemory ${maxmem}' > /etc/redis.conf"
    docker exec -i "$container" /bin/sh -c "echo 'maxmemory-policy ${policy}' >> /etc/redis.conf"
    
    # Apply settings immediately
    docker exec -i "$container" redis-cli CONFIG SET maxmemory "$maxmem"
    docker exec -i "$container" redis-cli CONFIG SET maxmemory-policy "$policy"
    
    # Verify settings
    echo "Verifying settings for $container:"
    docker exec -i "$container" redis-cli CONFIG GET maxmemory
    docker exec -i "$container" redis-cli CONFIG GET maxmemory-policy
}

# Function to apply optimizations
apply_optimizations() {
    check_docker
    check_compose
    check_config
    echo "Applying container optimizations..."
    
    # Optimize Redis Cache (using 75% of allocated memory with allkeys-lru policy)
    if docker ps | grep -q exp-redis-cache; then
        optimize_redis "exp-redis-cache-1" "768mb" "allkeys-lru"
    fi
    
    # Optimize Redis Queue (using 75% of allocated memory with volatile-lru policy)
    if docker ps | grep -q exp-redis-queue; then
        optimize_redis "exp-redis-queue-1" "768mb" "volatile-lru"
    fi
    
    echo "Container optimizations have been applied"
    echo "Would you like to rebuild the containers now? (y/n)"
    read -r answer
    if [ "$answer" = "y" ]; then
        rebuild_containers
    else
        echo "Remember to rebuild containers later for changes to take effect"
    fi
    get_status
}

# Function to remove optimizations
remove_optimizations() {
    check_docker
    check_compose
    check_config
    echo "Removing container optimizations..."
    
    # Reset Redis Cache
    if docker ps | grep -q exp-redis-cache; then
        optimize_redis "exp-redis-cache-1" "0" "noeviction"
    fi
    
    # Reset Redis Queue
    if docker ps | grep -q exp-redis-queue; then
        optimize_redis "exp-redis-queue-1" "0" "noeviction"
    fi
    
    echo "Container optimizations have been removed"
    echo "Would you like to rebuild the containers now? (y/n)"
    read -r answer
    if [ "$answer" = "y" ]; then
        rebuild_containers
    else
        echo "Remember to rebuild containers later for changes to take effect"
    fi
    get_status
}

# Main script
case "$1" in
    apply)
        apply_optimizations
        ;;
    remove)
        remove_optimizations
        ;;
    status)
        get_status
        ;;
    rebuild)
        rebuild_containers
        ;;
    *)
        show_usage
        ;;
esac 