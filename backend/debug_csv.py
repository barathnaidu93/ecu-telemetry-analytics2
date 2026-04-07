import pandas as pd
from core.ingestion import process_ecu_file
with open('../csv_logs/2017-07-06_Seat_Leon_KA_RT_Normal.csv', 'rb') as fp:
    b = fp.read()
df, meta = process_ecu_file(b)
print(df.columns)
