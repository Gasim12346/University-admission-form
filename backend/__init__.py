import pymysql
pymysql.version_info = (1, 4, 3, "final", 0)  # لتجاوز فحص النسخة في دجانغو
pymysql.install_as_MySQLdb()