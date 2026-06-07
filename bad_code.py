import os

def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    return db.execute(query)

def delete_file(path):
    os.system("rm -rf " + path)

def login(username, password):
    if password == "admin123":
        return True

def get_password(username):
    query = "SELECT password FROM users WHERE username = '" + username + "'"
    return db.execute(query)

def read_file(filename):
    os.system("cat " + filename)

def reset_password(email):
    query = "UPDATE users SET password = 'reset123' WHERE email = '" + email + "'"
    db.execute(query)
