from flask import Flask, render_template

app = Flask(__name__)


@app.route('/')
def mainp(name = None):
    return render_template('00index.html', name=name)


@app.route('/about')
def about(name = None):
    return render_template('about.html', name=name)


@app.route('/participants')
def participants(name = None):
    return render_template('participants.html', name=name)


@app.route('/organizers')
def org(name = None):
    return render_template('01org.html', name=name)


@app.route('/science_committee')
def sccom(name = None):
    return render_template('02sccom.html', name=name)


@app.route('/organizing_committee')
def orgcom(name = None):
    return render_template('03orgcom.html', name=name)


@app.route('/programm')
def prog(name = None):
    return render_template('04programm.html', name=name)


@app.route('/location')
def loc(name = None):
    return render_template('05location.html', name=name)


@app.route('/registration')
def reg(name = None):
    return render_template('06registr.html', name=name)


@app.route('/arrangement_fee')
def arrfee(name = None):
    return render_template('07arrfee.html', name=name)


@app.route('/abstract_preparation')
def abstprep(name = None):
    return render_template('08abstprep.html', name=name)


@app.route('/information_support')
def infosup(name = None):
    return render_template('09infosup.html', name=name)


@app.route('/key_dates')
def keydates(name = None):
    return render_template('10keydates.html', name=name)


@app.route('/Ilyin')
def rt(name = None):
    return render_template('11ilyin.html', name=name)


@app.route('/residence')
def res(name = None):
    return render_template('12residence.html', name=name)


@app.route('/post-tour')
def ptour(name = None):
    return render_template('13posttour.html', name=name)


@app.route('/contact')
def contact(name = None):
    return render_template('14contact.html', name=name)


if __name__ == "__main__":
    app.run(host='0.0.0.0')
