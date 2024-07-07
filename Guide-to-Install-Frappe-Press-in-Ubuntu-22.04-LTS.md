# Guide-to-Install-Frappe-Press-in-Ubuntu-22.04-LTS
A complete Guide to Install Frappe Bench in Ubuntu 22.04 LTS and install Frappe/Press Application

### Pre-requisites 

      Python 3.6+
      Node.js 14+
      Redis 5                                       (caching and real time updates)
      MariaDB 10.3.x / Postgres 9.5.x               (to run database driven apps)
      yarn 1.12+                                    (js dependency manager)
      pip 20+                                       (py dependency manager)
      wkhtmltopdf (version 0.12.5 with patched qt)  (for pdf generation)
      cron                                          (bench's scheduled jobs: automated certificate renewal, scheduled backups)
      NGINX                                         (proxying multitenant sites in production)

###   Server Settings Update and Upgrade Packages
      sudo apt-get update -y
      sudo apt-get upgrade -y

#### Create a new user – (bench user)
      In linux, the root user processes escalated privileges to perform any tasks within the system. This is why it is not advisable to use this user on a daily basis. We will create a user that we can use, and this will be the user we will also use as the Frappe Bench User.
      
      sudo adduser [frappe-user]
      usermod -aG sudo [frappe-user]
      su [frappe-user] 
      cd /home/[frappe-user]
      Ensure you have replaced [frappe-user] with your username. eg. sudo adduser frappe

####  Install Required Packages
A software like ERPNext, which is built on Frappe Framework, requires a number of packages in order to run smoothly. These are the packages we will be installing in this step.
      
### Install git
   
    sudo apt-get install git

###  Install Python

    sudo apt-get install python3-dev python3.10-dev python3-setuptools python3-pip python3-distutils python3.10-venv -y

###  Install virtualenv
    
    sudo apt-get install virtualenv -y

###  Install MariaDB

    sudo apt-get install software-properties-common -y
    sudo apt install mariadb-server -y
    sudo mysql_secure_installation
    
    
###  MySQL database development files

    sudo apt-get install libmysqlclient-dev -y

###  Edit the mariadb configuration ( unicode character encoding )
      sudo nano /etc/mysql/my.cnf
      add this to the my.cnf  file
      [mysqld]
      character-set-client-handshake = FALSE
      character-set-server = utf8mb4
      collation-server = utf8mb4_unicode_ci
      [mysql]
      default-character-set = utf8mb4
   
### Restart the MYSQL Server
   sudo service mysql restart

###  Instal CURL, Node, NPM and Yarn
###  install Redis
    
    sudo apt-get install redis-server -y

### install Node.js 18 package

    sudo apt install curl 
    curl https://raw.githubusercontent.com/creationix/nvm/master/install.sh | bash
    source ~/.profile
    nvm install 18 

###   install Yarn

    sudo apt-get install npm -y

    sudo npm install -g yarn

### install wkhtmltopdf

    sudo apt-get install xvfb libfontconfig wkhtmltopdf -y
    

### install frappe-bench

    sudo pip3 install frappe-bench
    
    bench --version
    
###  initilise the frappe bench & install frappe latest version 

    bench init frappe-bench
    ###OR
    bench init --frappe-branch version-15 frappe-bench 
    
    cd frappe-bench/

### Change user directory permissions
    This will give the bench user execution permission to the home directory.
    chmod -R o+rx /home/[frappe-user]
    ###OR
    sudo chmod o+rx $HOME

###  create a site in frappe bench 
    
    bench new-site [site-name]
    
    bench use [site-name]

###  Install Press and other Apps
    
    bench get-app payments
    bench get-app erpnext
    ###OR
    bench get-app erpnext --branch version-15

    bench get-app bench https://github.com/yt-easytouch/easytouch_press.git 
    (Private)
    ###OR
    bench get-app bench get-app https://github.com/frappe/press


    bench --site [site-name] install-app payments
    bench --site [site-name] install-app press
    bench --site [site-name] install-app erpnext
    
    bench start

### Install a Stable Ansible Version
    ### befor subup production
    sudo pip install ansible==2.9.27

### Install Nginx:

    sudo apt install nginx -y
    sudo service nginx start

### Using Let's Encrypt to setup HTTPS


### Install SSL https Port
    bench config dns_multitenant on
    bench setup nginx
    sudo service nginx reload

### Install certbot
    sudo snap install --classic certbot
    sudo -H bench setup lets-encrypt [site-name]

    ### https://frappeframework.com/docs/user/en/bench/guides/lets-encrypt-ssl-setup


### Restart Supervisor and Launch Production Mode 
    
    sudo apt-get install supervisor
    sudo supervisorctl restart all
    sudo bench setup production [frappe-user]

    bench set-maintenance-mode off
    bench start
