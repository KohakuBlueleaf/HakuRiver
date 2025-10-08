import os
import re
import sys
import argparse


def parse_and_save_files(input_filepath, output_base_dir):
    """
    Parses a text file containing multiple file contents separated by markers
    and saves each content block to its corresponding file path.

    Args:
        input_filepath (str): The path to the input text file.
        output_base_dir (str): The base directory where the parsed files
                                should be saved. File paths in the markers
                                will be treated as relative to this directory.
    """
    start_marker_pattern = re.compile(r"--- START OF FILE (.+?) ---")
    end_marker_pattern = re.compile(r"--- END OF FILE (.+?) ---")

    try:
        with open(input_filepath, "r", encoding="utf-8") as f:
            input_content = f.read()
    except FileNotFoundError:
        print(f"Error: Input file '{input_filepath}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input file '{input_filepath}': {e}", file=sys.stderr)
        sys.exit(1)

    # Find all start and end markers in the entire content
    start_matches = list(start_marker_pattern.finditer(input_content))
    end_matches = list(end_marker_pattern.finditer(input_content))

    if not start_matches:
        print(
            f"No start markers ('{start_marker_pattern.pattern}') found in '{input_filepath}'. Nothing to parse."
        )
        sys.exit(0)

    # Ensure output base directory exists
    os.makedirs(output_base_dir, exist_ok=True)

    # Process each file block defined by a start marker
    for i, start_match in enumerate(start_matches):
        file_path = start_match.group(1).strip()
        # The actual content starts after the --- and the following newline
        content_start_index = start_match.end()

        # Find the newline character immediately after the start marker header line
        newline_after_start_header = input_content.find("\n", content_start_index)

        if newline_after_start_header == -1:
            # Edge case: Start marker is the very last line in the file with no trailing newline
            # Or the file ends immediately after the marker line. Assume content is empty or ends here.
            actual_content_start = content_start_index
        else:
            # Content starts *after* the newline following the header line
            actual_content_start = newline_after_start_header + 1

        # Find the corresponding end marker for this specific file_path *after* the content start index
        corresponding_end_match = None
        for end_match in end_matches:
            # Ensure the end marker is located AFTER where the content for this block starts
            if end_match.start() >= actual_content_start:
                # Check if the file path in the end marker matches the one from the start marker
                end_file_path = end_match.group(1).strip()
                if end_file_path == file_path:
                    corresponding_end_match = end_match
                    break  # Found the first matching end marker for this file_path after the content started

        if corresponding_end_match:
            # Content ends right before the start of the end marker
            content_end_index = corresponding_end_match.start()
            raw_content = input_content[actual_content_start:content_end_index]
        else:
            # If no matching end marker found, assume content goes to the end of the input
            # (or the start of the next file block, which the loop structure handles)
            # In the format provided, if an end marker is missing, the content extends to the end of the input string.
            raw_content = input_content[actual_content_start:]
            print(
                f"Warning: No matching end marker found for '{file_path}' starting at index {start_match.start()}. Assuming content goes to end of input.",
                file=sys.stderr,
            )

        # Trim leading/trailing whitespace (including newlines) from the extracted content
        final_content = raw_content.strip()

        if not file_path:
            print(
                f"Warning: Skipping block {i+1} due to empty file path.",
                file=sys.stderr,
            )
            continue

        # Construct the full output path by joining the base directory and the file path
        output_path = os.path.join(output_base_dir, file_path)

        # Create parent directories if they don't exist
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                print(f"Created directory: {output_dir}")
            except OSError as e:
                print(
                    f"Error creating directory {output_dir} for '{file_path}': {e}",
                    file=sys.stderr,
                )
                continue  # Skip saving this file if directory creation failed
            except Exception as e:
                print(
                    f"Unexpected error creating directory {output_dir} for '{file_path}': {e}",
                    file=sys.stderr,
                )
                continue

        # Save the content to the file
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(final_content)
            print(f"Saved: {output_path}")
        except IOError as e:
            print(f"Error saving file '{output_path}': {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unexpected error saving file '{output_path}': {e}", file=sys.stderr)

    print("\nParsing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse multi-file output and save contents to individual files.",
        formatter_class=argparse.RawTextHelpFormatter,  # Preserve newline in help
    )
    parser.add_argument(
        "input_file",
        help="Path to the input text file containing the concatenated file contents "
        "with '--- START OF FILE ... ---' and '--- END OF FILE ... ---' markers.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Base directory where the parsed files will be saved.\n"
        "Paths specified in the START/END markers will be relative to this directory.\n"
        "Defaults to the current working directory ('.').",
    )

    args = parser.parse_args()

    parse_and_save_files(args.input_file, args.output_dir)
