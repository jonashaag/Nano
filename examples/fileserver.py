import os
from nano import NanoApplication, HttpError

app = NanoApplication()

@app.route('(?P<path>.+)')
def view(env, path):
    path = path.lstrip('/')
    relpath = os.path.join(os.getcwd(), path)
    if os.path.isdir(relpath):
        return index(relpath, path)
    elif os.path.isfile(relpath):
        return open(relpath)
    else:
        raise HttpError(404, 'Not Found')

def index(absdir, reldir):
    html = ['<ul>']
    for f in os.listdir(absdir):
        html.extend(['<li>', '<a href="/', os.path.join(reldir, f), '">', f, '</a></li>'])
    html.append('</ul>')
    return 200, {'Content-Type' : 'text/html'}, ''.join(html)

if __name__ == '__main__':
    import bjoern
    bjoern.run(app, '0.0.0.0', 8080)
