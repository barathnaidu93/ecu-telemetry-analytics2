import pandas as pd
df = pd.DataFrame([["1", "2", "3"], ["4", "5", "6"]], columns=["time", "RPM", "time"])
print(df)
cols = {}
for i in range(len(df.columns)):
    cols[i] = pd.to_numeric(df.iloc[:, i], errors='coerce')
new_df = pd.DataFrame(cols)
new_df.columns = df.columns
print(new_df)
