import configparser
import csv
import datetime
import os
import time

import requests
from bs4 import BeautifulSoup
from currency_converter import CurrencyConverter
from rich.console import Console
from tenacity import retry, stop_after_attempt

from constants import (
    CAPSULE_HREFS,
    CAPSULE_NAMES,
    CAPSULE_NAMES_GENERIC,
    CAPSULE_PAGES,
    CASE_HREFS,
    CASE_NAMES,
    CASE_PAGES,
    CONFIG_FILE,
    OUTPUT_FILE,
)


class Scraper:
    def __init__(self):
        self.api_key = None
        self.use_proxy = False

        self.case_quantities = []
        self.rmr_quantities = []
        self.stockholm_quantities = []
        self.antwerp_quantities = []
        self.rio_quantities = []
        self.paris_quantities = []

        self.total_price = 0
        self.total_price_euro = 0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
            }
        )
        self.console = Console()

        config = self.parse_config()
        self.set_config(config)

    def parse_config(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        return config

    def set_config(self, config):
        self.use_proxy = bool(config.get("Proxy API Key", "Use_Proxy"))
        self.api_key = config.get("Proxy API Key", "API_Key")

        for capsule_name in CAPSULE_NAMES:
            config_capsule_name = capsule_name.replace(" ", "_")
            if "RMR" in capsule_name:
                self.rmr_quantities.append(
                    int(config.get("2020 RMR", config_capsule_name))
                )
            elif "Stockholm" in capsule_name:
                self.stockholm_quantities.append(
                    int(config.get("Stockholm", config_capsule_name))
                )
            elif "Antwerp" in capsule_name:
                self.antwerp_quantities.append(
                    int(config.get("Antwerp", config_capsule_name))
                )
            elif "Rio" in capsule_name:
                self.rio_quantities.append(int(config.get("Rio", config_capsule_name)))
            elif "Paris" in capsule_name:
                self.paris_quantities.append(
                    int(config.get("Paris", config_capsule_name))
                )

        for case_name in CASE_NAMES:
            config_case_name = case_name.replace(" ", "_")
            self.case_quantities.append(int(config.get("Cases", config_case_name)))

    @retry(stop=stop_after_attempt(3))
    def get_page(self, url):
        if self.use_proxy:
            page = requests.get(
                url=url,
                proxies={
                    "http": f"http://{self.api_key}:@smartproxy.crawlbase.com:8012",
                    "https": f"http://{self.api_key}:@smartproxy.crawlbase.com:8012",
                },
                verify=False,
            )
        else:
            page = self.session.get(url)

        return page

    def scrape_prices(self):
        for capsule_page_url in CAPSULE_PAGES:
            if "rmr" in capsule_page_url:
                capsule_name = "2020 RMR"
                capsule_quantities = self.rmr_quantities
                capsule_hrefs = CAPSULE_HREFS[0:3]
                capsule_names_generic = CAPSULE_NAMES_GENERIC[0:3]
            elif "stockholm" in capsule_page_url:
                capsule_name = "Stockholm"
                capsule_quantities = self.stockholm_quantities
                capsule_hrefs = CAPSULE_HREFS[3:8]
                capsule_names_generic = CAPSULE_NAMES_GENERIC[0:4] + [
                    CAPSULE_NAMES_GENERIC[-1]
                ]
            elif "antwerp" in capsule_page_url:
                capsule_name = "Antwerp"
                capsule_quantities = self.antwerp_quantities
                capsule_hrefs = CAPSULE_HREFS[8:15]
                capsule_names_generic = CAPSULE_NAMES_GENERIC[0:7]
            elif "rio" in capsule_page_url:
                capsule_name = "Rio"
                capsule_quantities = self.rio_quantities
                capsule_hrefs = CAPSULE_HREFS[15:22]
                capsule_names_generic = CAPSULE_NAMES_GENERIC[0:7]
            elif "paris" in capsule_page_url:
                capsule_name = "Paris"
                capsule_quantities = self.paris_quantities
                capsule_hrefs = CAPSULE_HREFS[22:29]
                capsule_names_generic = CAPSULE_NAMES_GENERIC[0:7]

            self.scrape_prices_capsule(
                capsule_page_url,
                capsule_hrefs,
                capsule_name,
                capsule_names_generic,
                capsule_quantities,
            )

        self.scrape_prices_case(
            self.case_quantities, CASE_PAGES, CASE_HREFS, CASE_NAMES
        )

    def scrape_prices_capsule(
        self,
        capsule_page_url,
        capsule_hrefs,
        capsule_name,
        capsule_names_generic,
        capsule_quantities,
    ):
        if any([quantity > 0 for quantity in capsule_quantities]):
            self.console.print(f"[bold magenta]------------{capsule_name}-------------")
            page = self.get_page(capsule_page_url)
            soup = BeautifulSoup(page.content, "html.parser")

            for href_index, href in enumerate(capsule_hrefs):
                if capsule_quantities[href_index] > 0:
                    try:
                        listing = soup.find("a", attrs={"href": f"{href}"})
                        if not listing:
                            self.console.print("[bold red][!] Failed to load.")
                            break

                        price_span = listing.find(
                            "span", attrs={"class": "normal_price"}
                        )
                        price_str = price_span.text.split()[2]
                        price = float(price_str.replace("$", ""))
                        price_total = round(
                            float(capsule_quantities[href_index] * price), 2
                        )

                        self.console.print(capsule_names_generic[href_index])
                        self.console.print(
                            f"{price} --> ${price_total} ({capsule_quantities[href_index]})"
                        )

                        self.total_price += price_total

                    except ValueError:
                        self.console.print("[bold red][!] Failed to load.")
                        break

    def scrape_prices_case(
        self, case_quantities, case_page_urls, case_hrefs, case_names
    ):
        for index, case_quantity in enumerate(case_quantities):
            if case_quantity > 0:
                self.console.print(
                    f"[bold magenta]------------{case_names[index]}-----------------------------------"[
                        :41
                    ]
                )
                page = self.get_page(case_page_urls[index])
                soup = BeautifulSoup(page.content, "html.parser")

                listing = soup.find("a", attrs={"href": case_hrefs[index]})
                if not listing:
                    self.console.print("[bold red][!] Failed to load.")

                else:
                    try:
                        price_class = listing.find(
                            "span", attrs={"class": "normal_price"}
                        )
                        price_str = price_class.text.split()[2]
                        price = float(price_str.replace("$", ""))
                        price_total = round(float(case_quantity * price), 2)

                        self.console.print(
                            f"{price} --> ${price_total} ({case_quantity})"
                        )

                        self.total_price += price_total

                    except ValueError:
                        self.console.print("[bold red][!] Failed to load.")

                    if not self.use_proxy:
                        time.sleep(1)

    def print_total(self):
        self.console.print("[bold green]------------USD Total--------------------")
        self.console.print(f"${self.total_price:.2f}")

        self.total_price_euro = CurrencyConverter().convert(self.total, "USD", "EUR")
        self.console.print("[bold green]------------EUR Total--------------------")
        self.console.print(f"€{self.total_price_euro:.2f}")
        self.console.print("[bold green]-----------------------------------------")

    def save_to_file(self):
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")

        if not os.path.isfile(OUTPUT_FILE):
            open(OUTPUT_FILE, "w").close()

        with open(OUTPUT_FILE, "r", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            last_row = None
            for row in reader:
                last_row = row
            if last_row:
                last_date_str = last_row[0][:10]
            else:
                last_date_str = ""

        if date != last_date_str:
            today = now.strftime("%Y-%m-%d %H:%M:%S")
            total = f"{self.total_price:.2f}$"
            total_euro = f"{self.total_price_euro:.2f}€"
            with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([today, total])
                writer.writerow([today, total_euro])
