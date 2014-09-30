CloudMan Development
--------------------

Setup your shell environment for CloudMan development (only need to do this once):

    wget -qO- https://raw.github.com/brainsik/virtualenv-burrito/master/virtualenv-burrito.sh | $SHELL
    . $HOME/.venvburrito/startup.sh
    mkvirtualenv cm
    workon cm
    pip install -r requirements.txt -r dev_requirements.txt

Load CloudMan virtual envrionment (once per shell):

    . $HOME/.venvburrito/startup.sh
    workon cm

Run tests:

    nosetests

