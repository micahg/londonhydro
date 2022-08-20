# London Hydro Monitor

Monitors London Hydro usage and tells your:

* average consumption (for the day prior)
* max consumption (for a one hour period for the day prior)
* total consumption (for the day prior)

## Dependencies

* requests
* pandas

## Running

To run, you need the following:

* London Hydro Electricity Account
* London Hydro Username
* London Hydro Password

... and if you want an email, you need:

* GMail account name
* GMail token (not a password)

And run like so:

```
python londonhydro.py -e LH_ACCT -u LH_USER -p LH_PASS -g GMAIL_USER -t GMAIL_TOKEN
```

If you want to run that daily (like at 6am), use:

```
crontab -e
```

and then add:

```
0 6 * * * python3 londonhydro/londonhydro.py -e LH_ACCT -u LH_USER -p LH_PASS -g GMAIL_USER -t GMAIL_TOKEN
```