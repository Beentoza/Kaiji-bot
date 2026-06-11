import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
get_connections_list = "SELECT pid, usename, datname, client_addr, application_name, backend_start, state, state_change, query FROM pg_stat_activity ORDER BY backend_start;"
TOKEN = os.getenv("DATABASE_URI")
with psycopg2.connect(str(TOKEN)) as connection:
	with connection.cursor() as cursor:
		cursor.execute(get_connections_list)
		rows = cursor.fetchall()

		print("PID\tState\tQuery")
		for row in rows:
			if row[1] == "postgres" and row[4] == "Supavisor":
				print(f"{row[0]}\t{row[6]}\t{row[8][:30]}...")
