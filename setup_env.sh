#!/bin/bash

# Check if list of programs are installed
is_installed(){
    local current=0
    for cmd in "$@"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "Check passed, $cmd installed"
        else
            echo "$cmd is not installed. Please install"
            current=1
            break
        fi
    done
    return $current 
}

# Setup python env
setup_env(){
    if ! is_installed python3; then
        echo "Missing dependency: python3"
        return 1
    fi

    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
    echo "Environment ready. Activate with: source venv/bin/activate"
}

clean_venv(){
    rm -rf ./venv
    echo "Removed venv"
}

# Print usage information
print_help(){
	cat <<-EOF
	Usage: ./setup_env.sh [command]

	Commands:
	  -s, --setup    Create the venv and install dependencies (default)
	  -c, --clean    Remove the virtual environment
	  -h, --help     Show this help message

	Examples:
	  ./setup_env.sh             # runs setup (default)
	  ./setup_env.sh --clean     # delete the venv
	EOF
}

parse_command(){
    local command="${1:---setup}"
    case "$command" in
        -s|--setup)
            setup_env
            ;;
        -c|--clean)
            clean_venv
            ;;
        help|-h|--help)
            print_help
            ;;
        *)
            echo "Unknown command: $command"
            print_help
            return 1
            ;;
    esac
}

parse_command "$@"