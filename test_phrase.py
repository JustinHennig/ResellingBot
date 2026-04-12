from bot.scraper import _query_phrase_matches

cases = [
    ('samsung s24',       'Galaxy S 24, 5G, 128 GB Samsung Galaxy S 24',  True,  'Spaced S 24'),
    ('samsung s24',       'samsung galaxy s 24 256gb',                    True,  'Spaced S 24 galaxy'),
    ('samsung s24',       'samsung s24 256gb schwarz',                    True,  'Normal S24'),
    ('samsung s24',       'samsung galaxy s24',                           True,  'Galaxy S24'),
    ('samsung s24',       'samsung s21 tausch s22 s23 s24',               False, 'Tausch list'),
    ('samsung s23 ultra', 'samsung galaxy s23 ultra 256gb',               True,  'S23 Ultra'),
    ('samsung a55',       'Samsung Galaxy A 55 5G 128GB',                 True,  'Spaced A 55'),
    ('iphone 14 pro',     'iphone 12 blau tausch 13 14 15 16 17 pro',     False, 'Tausch iPhone list'),
    ('iphone 14 pro',     'iphone 14 pro 128gb neuwertig',                True,  'Real iPhone 14 Pro'),
    ('iphone 14 pro max', 'apple iphone 14 pro max 256gb wie neu',        True,  'iPhone 14 Pro Max'),
    ('iphone 16',         'iphone 12 pro 16 gb blau',                     False, 'Storage 16 gb separate'),
    ('iphone 16',         'iphone 12 pro 16gb blau',                      False, 'Storage 16gb joined'),
    ('iphone 16',         'iphone 16 128gb schwarz',                      True,  'Real iPhone 16'),
    ('samsung s23',       'samsung s21 tausch s22 s23',                   False, 'Tausch Samsung short'),
    ('pixel 9 pro xl',    'google pixel 9 pro xl 256gb',                  True,  'Pixel 9 Pro XL'),
    # Samsung "Galaxy" without "Samsung" in text
    ('samsung s24',       'Galaxy S24 256GB',                             True,  'Galaxy S24 no Samsung'),
    ('samsung s24',       'Galaxy S 24 256GB',                            True,  'Galaxy S 24 spaced no Samsung'),
    ('samsung s24',       'galaxy s24 wie neu',                           True,  'Galaxy S24 lowercase'),
    ('samsung s24',       'Samsung Galaxy S24 schwarz',                   True,  'Samsung Galaxy S24'),
    ('samsung s23 ultra', 'Galaxy S23 Ultra 256GB',                       True,  'Galaxy S23 Ultra no Samsung'),
]

all_pass = True
for query, text, expected, label in cases:
    result = _query_phrase_matches(query, text)
    ok = result == expected
    all_pass = all_pass and ok
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {label}: got {result} (expected {expected})")

print()
print("All tests passed!" if all_pass else "SOME TESTS FAILED")
