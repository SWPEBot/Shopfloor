#!/bin/bash
# Script to replace a file within factory.par
# Usage: bash repack_par.sh --replace <target_path> <source_file>
# Example1: bash repack_par.sh --replace cros/factory/gooftool/wipe.py \
# new_wipe.py
# Example2: bash repack_par.sh --replace cros/factory/gooftool/wipe.py \
# /usr/local/factory/py/gooftool/wipe.py --inplace


# Default values
FACTORY_PAR="factory.par"
TEMP_DIR="temp"
NEW_ZIP="factory.par.zip"
NEW_FACTORY_PAR="factory.par.new"
HEADER="header"


# Create temp directory
CreateTempDir() {
  # If the temp directory exists, remove it
  if [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
  fi
  echo "Create temp directory $TEMP_DIR"
  # Create the temp directory
  mkdir "$TEMP_DIR"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to create temporary directory $TEMP_DIR"
    exit 1
  fi
}

# Get header from factory.par
GetHeaderFromFactoryPar() {
  unzip_output=$(unzip -l "$FACTORY_PAR" 2>&1)
  header_size=$(echo "$unzip_output" | grep "extra bytes" | grep -o '[0-9]\+')
  echo "Header size: $header_size"
  if [ -z "$header_size" ]; then
    echo "Error: Could not determine header size for $FACTORY_PAR."
    exit 1
  fi
  # dd header from factory.par to header file
  dd if="$FACTORY_PAR" bs=1 count="$header_size" of="$HEADER" 2>/dev/null
}

# Unzip factory.par
UnzipFactoryPar() {
  unzip -o "$FACTORY_PAR" -d "$TEMP_DIR" 2>&1
}

# Replace target with source
CopySourceToTarget() {
  cp "$SOURCE_FILE" "$TEMP_DIR/$TARGET_PATH"
  echo "Copied source file $SOURCE_FILE to $TEMP_DIR/$TARGET_PATH"
}

# Zip the temp directory
ZipTempDir() {
  cd "$TEMP_DIR"
  zip -rq "../$NEW_ZIP" * >/dev/null 2>&1
  cd ".."
}

# Merge header and new zip file
MergeHeaderAndZip() {
  local output_file
  if [ "$INPLACE" = "true" ]; then
    output_file="$FACTORY_PAR"
  else
    output_file="$NEW_FACTORY_PAR"
  fi
  cat "$HEADER" "$NEW_ZIP" >"$output_file"
  chmod 755 "$output_file"

  if [ "$INPLACE" = "true" ]; then
    echo "Successfully updated factory.par"
  else
    echo "Generated new file: $NEW_FACTORY_PAR"
  fi
}

# Clean up temp directory
CleanUp() {
  rm -rf "$TEMP_DIR" "$NEW_ZIP" "$HEADER"
}

# Parse and validate arguments
ParseArgs() {
  # Show usage information
  ShowUsage() {
    cat << EOF
Usage: $0 --replace <target_path> <source_file> [--inplace]

Arguments:
  --replace      Required, specify the replace operation
  target_path    Required, target file path in factory.par
  source_file    Required, source file path to replace with
  --inplace      Optional, modify original factory.par directly

Examples:
  $0 --replace cros/factory/gooftool/wipe.py new_wipe.py
  $0 --replace cros/factory/gooftool/wipe.py /usr/local/factory/py/gooftool/wipe.py --inplace
EOF
    exit 1
  }

  # Check argument count
  if [ "$#" -lt 1 ]; then
    ShowUsage
  fi

  # Parse arguments
  local args=("$@")
  local i=0
  while [ $i -lt ${#args[@]} ]; do
    case "${args[$i]}" in
      --replace)
        if [ $((i + 2)) -ge ${#args[@]} ]; then
          echo "Error: --replace requires two arguments: <target_path> <source_file>" >&2
          ShowUsage
        fi
        TARGET_PATH="${args[$((i + 1))]}"
        SOURCE_FILE="${args[$((i + 2))]}"
        i=$((i + 3))
        ;;
      --inplace)
        INPLACE="true"
        i=$((i + 1))
        ;;
      --help|-h)
        ShowUsage
        ;;
      *)
        echo "Error: Unknown argument '${args[$i]}'" >&2
        ShowUsage
        ;;
    esac
  done

  # Validate required arguments
  if [ -z "${TARGET_PATH:-}" ] || [ -z "${SOURCE_FILE:-}" ]; then
    echo "Error: Missing required arguments" >&2
    ShowUsage
  fi

  # Validate file existence
  if [ ! -f "$FACTORY_PAR" ]; then
    echo "Error: factory.par file not found: $FACTORY_PAR" >&2
    exit 1
  fi

  if [ ! -f "$SOURCE_FILE" ]; then
    echo "Error: Source file not found: $SOURCE_FILE" >&2
    exit 1
  fi
}

# Main function
main() {
  # Parse arguments
  ParseArgs "$@"
  # Execute replacement steps
  CreateTempDir
  GetHeaderFromFactoryPar
  UnzipFactoryPar
  CopySourceToTarget
  ZipTempDir
  MergeHeaderAndZip
  CleanUp
}

# Call main function with all arguments
main "$@"
