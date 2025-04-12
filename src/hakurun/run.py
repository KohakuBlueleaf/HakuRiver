import sys
import os
import argparse
import importlib
import shlex
from itertools import product
from subprocess import Popen
from .logger import logger  # Assumes logger is configured elsewhere


def import_function(import_string):
    """Imports a function or module specified by a string ('module:function' or 'module').

    Args:
        import_string: The string specifying the module and optional function.

    Returns:
        The imported function object, or None if only a module was specified.
    """
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())

    module_name, *function_name_parts = import_string.split(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        # Take import_string as general scritps:
        return import_string

    if not function_name_parts:
        return None

    function_name = function_name_parts[0]
    function = getattr(module, function_name)
    return function


def parse_spanning(arg_str):
    """Parses an argument string, expanding it if it uses spanning syntax.
    Arguments without the "span:" prefix are returned unchanged within a list.

    Args:
        arg_str: The string argument to parse.

    Returns:
        A list containing the expanded values (int for ranges, str otherwise),
        or a single-element list with the original string if no spanning syntax
        was detected.
    """
    if not arg_str.startswith("span:"):
        return [arg_str]

    span_content = arg_str.split("span:", 1)[1].strip()

    if (
        span_content.startswith("{")
        and span_content.endswith("}")
        and ".." in span_content
    ):
        try:
            start, end = span_content[1:-1].split("..")
            return list(range(int(start.strip()), int(end.strip()) + 1))
        except ValueError as e:
            raise ValueError(
                f"Invalid range format in '{arg_str}'. Expected 'span:{{int..int}}'."
            ) from e
    elif span_content.startswith("[") and span_content.endswith("]"):
        content = span_content[1:-1].strip()
        if not content:
            return []
        return [x.strip() for x in content.split(",")]
    else:
        # If it starts with "span:" but doesn't match known patterns,
        # return the content after "span:" as a single string value.
        # This could be debated, maybe raise error? For now, treat as literal.
        return [span_content]


def make_arg_product(args_list):
    """Generates argument combinations by expanding arguments with spanning syntax.

    Args:
        args_list: The list of application arguments (strings) potentially
                   containing "span:" prefixes for expansion.

    Returns:
        An iterator yielding tuples. Each tuple represents one argument
        combination after spanning is applied.
    """
    all_span_lists = []
    for idx, arg_str in enumerate(args_list):
        try:
            all_span_lists.append(parse_spanning(arg_str))
        except ValueError as e:
            logger.error(
                f"Error parsing spanning argument at index {idx} ('{arg_str}'): {e}",
            )
            sys.exit(1)

    return product(*all_span_lists)


def runner():
    """Runs a Python function or module multiple times with expanded arguments.

    This utility takes a target Python module/function and a list of arguments.
    Arguments prefixed with "span:" are expanded according to their syntax:
    - Integer range: "span:{start..end}" (e.g., "span:{1..2}" -> 1, 2)
    - List: "span:[item1, item2]" (e.g., "span:[a,b]" -> "a", "b")

    It generates the Cartesian product of all expanded arguments and runs the
    target for each combination, either sequentially or in parallel via
    subprocesses. Output is managed via a configured logger.

    Usage Example:
    ----------------
    Given demo.py:
    ```python
    # demo.py
    import sys, os
    print(f"Running demo.py with args: {sys.argv[1:]}, PID: {os.getpid()}")
    ```

    Command:
    ```bash
    hakurun --parallel demo_hakurun "span:{1..2}" "test" "span:[0, 99]"
    ```

    Example Output (order may vary with --parallel):
    ```
    [HakuRun]-|xx|-INFO: Running 4 tasks in parallel via subprocess...
    [HakuRun]-|xx|-INFO:   Task 1/4: python -m hakurun.run demo_hakurun 1 test 0
    [HakuRun]-|xx|-INFO:   Task 2/4: python -m hakurun.run demo_hakurun 1 test 2
    [HakuRun]-|xx|-INFO:   Task 3/4: python -m hakurun.run demo_hakurun 2 test 0
    [HakuRun]-|xx|-INFO:   Task 4/4: python -m hakurun.run demo_hakurun 2 test 2
    [HakuRun]-|xx|-INFO: Waiting for parallel tasks to complete...
    ['demo_hakurun', '2', 'test', '0']
    ['demo_hakurun', '1', 'test', '99']
    ['demo_hakurun', '1', 'test', '0']
    ['demo_hakurun', '2', 'test', '99']
    [HakuRun]-|xx|-INFO: All parallel tasks finished successfully.
    ```
    """
    parser = argparse.ArgumentParser(
        description=runner.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run the generated tasks in parallel using subprocesses.",
    )

    parser.add_argument(
        "app",
        help="Target to run, in '<module>:<function>' or '<module>' format. "
        "If only '<module>' is given, the module is imported (useful for "
        "module-level execution), but no specific function is called.",
    )
    parser.add_argument(
        "app_args",
        nargs=argparse.REMAINDER,
        metavar="ARGUMENTS...",
        help="Arguments to pass to the target. Use 'span:{start..end}' or "
        "'span:[a,b,...]' syntax on arguments to generate combinations.",
    )
    args = parser.parse_args()

    try:
        all_arg_combinations = list(make_arg_product(args.app_args))
    except ValueError:
        sys.exit(1)

    num_tasks = len(all_arg_combinations)

    if num_tasks == 0:
        logger.error(
            "No argument combinations generated (perhaps an empty list 'span:[]' was used?). Exiting.",
        )
        sys.exit(0)

    if num_tasks > 1:
        logger.info(
            f"Running {num_tasks} tasks "
            f"{'in parallel' if args.parallel else 'sequentially'} via subprocess..."
        )
        processes = []
        base_command = [sys.executable, "-m", "hakurun.run", args.app]

        for i, arg_combination in enumerate(all_arg_combinations):
            str_args_list = [str(a) for a in arg_combination]
            cmd = base_command + str_args_list
            logger.info(f"  Task {i+1}/{num_tasks}: {shlex.join(cmd)}")

            try:
                p = Popen(cmd, cwd=os.getcwd(), env=os.environ)
            except OSError as e:
                logger.error(
                    f"Error starting subprocess for task {i+1}: {e}",
                )
                continue

            if args.parallel:
                processes.append((p, cmd))
            else:
                retcode = p.wait()
                if retcode != 0:
                    logger.warning(
                        f"Task {i+1} ({shlex.join(cmd)}) exited with code {retcode}",
                    )

        if args.parallel:
            logger.info("Waiting for parallel tasks to complete...")
            all_success = True
            for i, (task_proc, task_cmd) in enumerate(processes):
                retcode = task_proc.wait()
                if retcode != 0:
                    all_success = False
                    logger.warning(
                        f"Parallel task {i+1} ({shlex.join(task_cmd)}) exited with code {retcode}",
                    )
            if all_success:
                logger.info("All parallel tasks finished successfully.")
            else:
                logger.warning("Some parallel tasks failed.")

    else:
        single_arg_combination = all_arg_combinations[0]
        # Modify sys.argv for the target function if it relies on it.
        # Note: This is a global change affecting only this single direct run.
        original_argv = sys.argv
        sys.argv = [args.app] + [
            str(a) for a in single_arg_combination
        ]  # Use stringified args for sys.argv
        logger.debug(f"Set sys.argv for direct run: {sys.argv}")

        try:
            func = import_function(args.app)
            if isinstance(func, str):
                # general script calling
                p = Popen(
                    [func] + list(single_arg_combination),
                    cwd=os.getcwd(),
                    env=os.environ,
                )
                p.wait()
            elif func is not None:
                logger.debug(
                    f"Calling function {func.__name__} with args: {single_arg_combination!r}"
                )
                # Call the function directly with potentially mixed types (int, str)
                func(*single_arg_combination)
            else:
                logger.debug(f"Module {args.app} imported, no function called.")

        except (ImportError, AttributeError) as e:
            logger.error(f"Error importing/finding target '{args.app}': {e}")
            sys.exit(1)
        except TypeError as e:
            logger.error(
                f"Error calling '{args.app}' with arguments {single_arg_combination!r}: {e}"
            )
            logger.error(
                "Check if the function signature matches the number and types of arguments provided."
            )
            sys.exit(1)
        except Exception as e:
            logger.error(
                f"Error during direct execution of '{args.app}':"
            )  # Use logger.exception to include traceback
            sys.exit(1)
        finally:
            # Restore original sys.argv regardless of success/failure
            sys.argv = original_argv


if __name__ == "__main__":
    runner()
