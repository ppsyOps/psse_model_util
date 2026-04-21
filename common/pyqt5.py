import sys
from PyQt5.QtWidgets import QApplication, QFileDialog
from pathlib import Path


def file_browser(caption: str = "Select File",
                 directory: str | Path = "",
                 options=None) -> Path:
    """
    Open a file dialog to select a file, starting from the given path or the
    current working directory if none is specified. Return the path to the
    selected file.

    Args:
        caption (str): The caption/title of the dialog.
        directory (str | Path): The initial directory the file dialog opens in. If
                            empty, defaults to the current working directory or
                            system default.
        options: valid PyQt5.QtWidgets.QFileDialog.Options

    Returns:
        str: The path to the selected file, or an empty string if no file was selected.
    """
    app = QApplication(sys.argv)  # Ensure a QApplication instance is available
    if not options:
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
    directory = Path(directory)
    file_path, _ = QFileDialog.getOpenFileName(parent=None, caption=caption,
                                               directory=str(directory),
                                               initialFilter="All Files (*);;Python Files (*.py)",
                                               options=options)
    return Path(file_path)


def _examples():
    # file_dialog example:
    # Example usage with a starting path. Replace 'C:/Users/' with a relevant path on your system.
    selectedFilePath = file_browser(caption='Select File', directory="//corp.pjm.com/shares/atc")
    print('file_dialog: ', selectedFilePath or "No file selected.")


if __name__ == '__main__':
    _examples()
