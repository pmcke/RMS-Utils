import os
import time
import logging

# Configure logging
LOG_FILE = 'delete_old_files.log'
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Folder to clean up
FOLDER_PATH = os.path.expanduser('~/Lux_data_auto')

# Age threshold: 14 days
AGE_THRESHOLD = 14 * 24 * 60 * 60


def delete_old_files(folder_path, age_threshold):
    current_time = time.time()

    if not os.path.exists(folder_path):
        logging.error(f"Folder does not exist: {folder_path}")
        return

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)

        # Ignore directories
        if not os.path.isfile(file_path):
            continue

        # Never delete log or JSON files
        if filename.lower().endswith(('.log', '.json')):
            continue

        file_mod_time = os.path.getmtime(file_path)

        if current_time - file_mod_time > age_threshold:
            try:
                os.remove(file_path)
                logging.info(f"Deleted old file: {file_path}")
            except Exception as e:
                logging.error(f"Error deleting {file_path}: {e}")


if __name__ == "__main__":
    logging.info("Starting cleanup script")
    delete_old_files(FOLDER_PATH, AGE_THRESHOLD)
    logging.info("Cleanup script completed")