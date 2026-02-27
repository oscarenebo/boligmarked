import pandas as pd
import matplotlib.pyplot as plt

# 1. Load your data
df = pd.read_csv('data/raw/merged/boliga_merged.csv')

# 2. Convert date column to actual datetime objects
df['soldDate'] = pd.to_datetime(df['soldDate'])

# 3. Filter for a specific Danish Zip Code (e.g., 2100 for Østerbro)
target_zip = 4400
zip_df = df[df['zipcode'] == target_zip].copy()

# filter for a specific property type villa = 1, rækkehus = 2, ejerlejlighed = 3, fritidshus = 4. Possible to choose more than one property type
property_types = [1, 2]  # Example: Villa and Rækkehus
zip_df = zip_df[zip_df['propertyType'].isin(property_types)]

# Remove outliers that have a price per m² above a set threshold
max_sqm_price = 50000  # Example threshold for outlier removal
zip_df = zip_df[zip_df['sqmPrice'] <= max_sqm_price]

# Using 'ME' (Month End), 'QE' (Quarter End), or 'YE' (Year End) for resample
trend = zip_df.set_index('soldDate')['sqmPrice'].resample('QE').median()

# 6. Plot the results
plt.figure(figsize=(10, 6))
trend.plot(linestyle='-', color='darkblue', marker='')
plt.title(f'Price Evolution for Zip Code {target_zip}')
plt.ylabel('Median Price per m² (DKK)')
plt.grid(True)
plt.show()