import os

direc = 'apartment_data/'
current_directory = os.getcwd()

# Get the list of files in the directory
files = os.listdir(direc)

# Filter the list to include only .json files
json_files = [file for file in files if file.endswith(".json")]

# Empty the contents of each .json file
for file in json_files:
    file_path = os.path.join(direc, file)
    with open(file_path, "w") as json_file:
        json_file.write("{}")

print("All .json files have been emptied.")