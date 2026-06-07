import os

def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(query)

def delete_file(path):
    os.system("rm -rf " + path)

def login(username, password):
    if password == "admin123":
        return True
