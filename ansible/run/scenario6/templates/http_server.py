from flask import Flask, request

app = Flask(__name__)

LOG_FILE = 'log.txt'

@app.route('/', methods=['POST'])
def log_post():
    data = request.get_data().decode('utf-8')
    with open(LOG_FILE, 'a') as f:
        f.write(data+ '\n')
    print(f"Logged: {data}")
    return 'Logged\n'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)

