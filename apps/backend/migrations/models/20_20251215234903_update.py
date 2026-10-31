from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."simulator_sessions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "messages" JSONB NOT NULL,
    "context" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_user_id" INT NOT NULL REFERENCES "backend"."company_users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_simulator_s_company_f36642" UNIQUE ("company_user_id")
);
COMMENT ON TABLE "backend"."simulator_sessions" IS 'Isolated sandbox session for testing AI agent.';
        COMMENT ON COLUMN "backend"."company_users"."role" IS 'OWNER: owner
ADMIN: admin
MANAGER: manager
VIEWER: viewer';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "backend"."company_users"."role" IS 'OWNER: owner
ADMIN: admin
VIEWER: viewer';
        DROP TABLE IF EXISTS "backend"."simulator_sessions";"""


MODELS_STATE = (
    "eJztXVlz27YW/isYPaUzbiZxlmY0d+6MbMuJbm3Jteg4bZThwBIksaYAmaS8tJP/fgHuC0"
    "hxlQgbL61D4kDEh+XsB/92VmSGdPP1MbTQghhPnS74t4PhCtE/Eu8OQAeu18Eb9sCCN7rd"
    "eOq00pD9GN6YlgGnFn0zh7qJ6KMZMqeGtrY0gulTvNF19pBMaUMNL4JHG6zdbZBqkQWyls"
    "igL77/oI81PEOPtHP3n+tbda4hfRb5YG3Gftt+rlpPa/vZAFundkP2azfqlOibFQ4ar5+s"
    "JcF+aw1b7OkCYWTQAbHuLWPDPp99nTtWb0TOlwZNnE8M0czQHG50KzTcnBhMCWb40a8x7Q"
    "Eu2K/8evj2/W/vP737+P4TbWJ/if/kt5/O8IKxO4Q2AkOl89N+Dy3otLBhDHCz/59A7ngJ"
    "DT50XvsYePST4+B5UGWh5z0I4AuWTE34reCjqiO8sJYMtA8fMtD62rs8/tK7fEVb/cJGQ+"
    "gydlb40H116LxjkAYQhr8sgaSCHlMWYYxMFEAz8FP63xT20SvTvNPDsL06732zEV09uW/O"
    "RsPPXvMQzMdno6MYusZGd86VvLj6BBJRPqLoEa7WBUEN0+wO105HHFQfiHE718lDEVTDNH"
    "K18nGdktUa4ie1EIOPEm1n9O2Atg5ezwSk+S2X1bugJGE8JQbSFvh39GSjOaAfBfGUx+Y9"
    "sTDoqX0o/vQWg/c0EMoM+OCLjrE1QgdJh4YsR/zpjY97J/2OjeYNnN4+QGOmpsHqyshUbC"
    "W6aiAdsi/mnK5Hbkenv1+6jTIQdjtVaJ9iwRzZvC5elaDwd/gWDNw5bhsEa4PMNlOrIggX"
    "Ti9iwcB2DzkkoV0T2U/JV6vDVfwJxHBhfzX7bfZLvA2Sobl6G2ir9urs33wabEdZGmSzWA"
    "K7EzAnBvB+71f2g+CcHiwKYf8F3oHwuhMDs3QnHC35uz8Ke2hszD+k5tys5uyvm2KSSZTq"
    "JYkm4VPR5pWFgAtRvCTQsuS50JavKtCFumofjrkluuje4ot08VVYA3riCWlx5EKbq6gg3C"
    "iTX0LrHJkmtDdSkseHXmezeNpQXTktc3L4AZ5p99psA3XgEoIHzVpqGEBgLQ0EZ0mGnpNm"
    "u5X7e8dp7k7JlP5NV5UKLYerSzZeIxt3Z4rLjNLN4FGqemw3jSMZMYW/PfyUwxROW6Wawu"
    "13MWMt0VO8CX28WSWO06jd1qXdsyGsczXuX3bBxkTGBPfG48FY6Q2VLoCmqbEvtyb4vDfs"
    "fWaNnIOLthv/OVb6511gPpkWWsUPhlzT8THPbHxMn4yP8bmwASw5Fx7tDk29Fnq0kuZe26"
    "ZIdwJ9OcF0M/cvh70zdThS+l1AgUQGhrqKiYXagTn9OQs5x2heG3CIRJqA+SZgukitDceA"
    "km8tB9Q7XM1rRGUBCmFyQV/0hyeD4ecucJvQw6PPzhcTsaPltDc465+wLjUdzSb4uDc87p"
    "/Zj6ZsdDp9WmapH77J4/d8k+72fBNf6itkQcZUk9Pyv/FomMY1A5rYZFxhis/3mTa1DoBO"
    "D9ofjU3Nf+YbPGWzAW42mm5p2HzNfva/zfiaGBjZGyK+9hk2xLQWht2L3UF8Q0DLgtPlCm"
    "GeWTEd/hhZm2aA/aBIM2Cgtc4shkVkxjBNqaNo96bdHYiMIeUmgeUJfWNpK5TCOSOUMURn"
    "Lulr7492stIOU/NGWH/q+K6DVNY6OO9TWfT8IrKYT3pKn705jPBW7+mruPDidwKuB8oXwP"
    "4J/hoN+/E177dT/mImkw7cWITKWQ8qnIU0E++pB0xkYjfrWcmJjVLWMLF72DjPZV4T/qwZ"
    "0rV7ZJSa2DitkFMryFR6w87co/TlkhjFDPERmlKm+D1sx7rdF2HzXF4HRphGujBCONZhgv"
    "c7ah+GuY3w4QWy3Xnh7MM6nD9OIMyVidophObFL3IwtcqN4YZL8VwYQSRVhvvCbiTD6wX0"
    "Lsjwehle32rbqgyvrxtRi2Ckkrl6T7QpZ++nI5sglAjzEfZdcWrR4zVJKQrGOzho7zZQ1+"
    "ba1I40VMvkM6T3IArMu17KUcTKZOak9yAxT8so0XVk+x8Knx8c0n2HKyhLBNi3ADIHVKoH"
    "wScCDYO7mQEdwbsVRww9exfIZKrcXFsUcV0lCKXzqrzzyo+TTBH+0qchSSnnocI8GCt1Tg"
    "zbwOC5xtVb9FRsSrI6kbNTbXbcEan28VMwRDCNfodRKBeXo+P+eNw/qQB7lCt8yBNH8iE9"
    "juRDIo6EweTG0anQYqFQjLuWBTy7JyG97vVAnjDCF0ht1HhMokw2Y6vlz+w0Pi9btNYkT6"
    "dP8dIHuMiwiNl6AMnpiWgtIBvTIqvqYLjdCIzEHN5VTf7t/SHy+J0ztRoCHq8TFAML6Whh"
    "wJV6Q6omQStuV0ekpd7yfIDYbt6qUAjo746WS4HrtcbaYDS1SNWz8pr1dux1JhgsO3A9p2"
    "bJRyWQbS7oqjnyTifVUuTz9MHPkA9c7TJBvrOLBHlZuUemx8tyRy2JjspT7kjmxguUGx/S"
    "ldM5u6dKb+fsvvpeb4DZ987G/QRvP0q+2zDfFSsJu3OvoQdnhcQEyNH1kCVZkwdsp2KfnA"
    "+GXQBnKw3zUrC/DvrX7EGou73nSMrcpmeRA2MDw7V5StG2sGjL2EEx3EIULwm0DNHWY6kV"
    "ZTPx7Oxx2Sy0NLZLtFIhaKT+abiuUgVvR7SWU+t8srmMmqa22tCBEkM16VCqOwjHXn9jpz"
    "uxFlwiZneBqUSzW/N3ixZKo8qg5yvkaYIhP2KGGhh2Wm437nqdgrVB5pruFDoDdxvtHwCx"
    "SQVwk/5/BigK9/RvezaBF52UNPNW7i1V8fQqqEndcze6Z6p0lx62ky7e1aZ1NlpI7eP7HG"
    "rjx/epaiN7FRWRd5o0tu/wpkbijA30N5paiLMOjwjREcQpuU0hshiYNw3aMYua2fIHRh6N"
    "RmcRlfpoEA+Qvzo/6l++emujSxtpjgSY1NscbFhEHWW9Ji8XL6vyTZJWLtYgB0T7R3X5XB"
    "LV9MjfOF2bgn1Fq6ilQ7yYU06UIbinTwSXWM5G+dlgsl2RCfDaS8yrhLtLW/WztFW3qA6X"
    "nNgaC3FJH4SMFGm1YfjlBro2aepjEfEcK58bKJ9u4PNi8WX9oLadTAcZ9rT0O14y8uBCNK"
    "LUANiJmo3MokWEwjSiQLnzaiy2BaIIqgGFxJSP6S16eiAGj3emK8FhmjYpwsLlfUu5WsrV"
    "dYiB9crVjcqUCXktnnyYIVc6PyElS8EkS1mZUkqULZV+HPnQwYW7QrfHsce62HeRrrFyad"
    "/54wA9wY7XlbVe3bDgdean7feGXXDjuKcnuE+bdAGiDTptWe4GuttoRgmnekAmneoplbh2"
    "foew+DX4pZxeGjr3Tvpi0EWJXtCikxpOUzmm+7nBuj0xwQn8il5g7e7JGvC7CHoSFr7oCV"
    "XecUXWNRT3snEf+fXnxdnUzXqvQqik2RsC0LZYHdTQRNWdtTz3eOA91OmE0EGFnhFjRtvJ"
    "YPKGTRQO9Ano0m0UPoEomvUOtDZnreZff3773QnHb/a9BGMV24rJxWGSl6RQZIjF/kFZUS"
    "jxAW8fgnllkvDqaJPJ35P3OEw4JAqmM2BX1pKGf+G4qjT8V+ap8kqqRs3/Fv2em41V7GqC"
    "KFWbAiCEywSQRuna7IPSwFXcwJXHRBNEHVS00AgFZ6OmGSr2rdZpAiF7s00epG2kOCicOE"
    "gXA7aq+dojPdQj1ZREtXM5ulKYY90gVBIwJviPq97Z4HTAHrkXpbGnxz2l/3l0+afa/3bR"
    "v1S6wD+X0OMaGaXuy2rgZhSC2SUmRSTMEImULgPpMsGh96NzX6I5FbuWCrlFXOt35H3maW"
    "s4LelBSZvKQ1e4Q/dvSyuigrvN93q0ltS/66+OQo9ojS7+EvmsUUox81kFyV/1hp1dRVOm"
    "nD+HzOTkxMoan7LG5+5qfO5HmEvUZuQIdLz6jelCHb965PZafAOT6GxmgQnx7IY8Apfcvi"
    "/FYuHmeAF6A2Dracnie8XIJyw2GU6XwI31Amx6wCu7LPcvYAlNQDDyu6DKlN/QWkILmHR4"
    "yJxg1m+0nt9SY++e7NJ/VHkDcD5nNaPob9NzUgd+fcKtF7zYlexlcEbTImx62desOj0BTZ"
    "ss9OKlKNIN9MiRmjKuCQ5I2oS8cL4RKbI+U5FVVkl6DhObeTttuVQRqZqkXexWk4oi7K2/"
    "cU2Fs2LapLGEr0/lKCux21XT9ZTEja7S9ty2zZsluPt3rhas0x2nE9Ea/fZNHi8dbZVqj7"
    "bfRWVCug0cR0wRNCNEovjqdhBax86bso5oj3aHl5cx0SOpvnR6V8qoC9jLCb7uH30ZjX7v"
    "ggd0syTkdoIvRmdndjr4mug6w7sM+PVfVraEdIPrGaEAKedCjG6H6HucqIIC2bQT35101U"
    "RUAeToFum4JillyfQ4qmtIf6MEph6dRDRccpuJDMXMeQGNNCqVNyohzBAoWlcjRLXDshq+"
    "eNbmqhrSSPccbDnSSPdMJ1aWMpcFSXZrkWuhMc6pa86zw/kVzzNMcEFp9Rx39YXd7A4lWB"
    "hks2bOdc8lC+YGWQEIzDWaanNtCly1jnNZX+Xuthv9vvv3EXoX+IWVzB/SJlji1DjIsAk6"
    "01jQIBghEtIaePgpjzXw8FO6NZC9E92MUiekjWRB+MdNcYt1nFQq/P5dxRYdcFlLq0+8S1"
    "Mr1fLvEc/YeqwMvva7wGkwwde9gTIYflZ74/GAyqVDpQseoMZCyVR2CzEbkhW0Ou8Ne59Z"
    "fpDXxmHZxgR/6Q1PRqenXUB35ozM5xNMFfpx/6QLpjoxHc276FS+y7M/3qXvj3eJ/eEPSQ"
    "0AKmBF4JFLc0JU68Q2n5uSDS8ZKz2kOUb2IuvpSLOijFXbk1zyXKwl0gz2TCc2YQZjvHiB"
    "ESpmB4tRvaDCG9KEWA90UVNLXuyiVC8JvCz7q4tKHQbYUFftwzG3BTa6THLUhJYW7ColtT"
    "1uUB9+OeNy21MlJw5hjEGWLzqUnvJUpOzQ8RJa505PYi3NRqsPKczIwPOGuMaHDF8IbSHD"
    "kIVzOey3DOUzCDuWRSj3WCaIUy2RnUOq4R7/VXmE26nSoOm1ISbBU8pqhcbpU0BkmmSftp"
    "DGYZ+e8JbOPlmykmSfwrFPtIKaXoR/+gQiMtBGPKBLaC7RTF1T/YBdnFwETA6pKIx0B8Bq"
    "ZjlfZIROOiHjmJqbNTL4ObfbYI2QyksYpZ/sGbpTpJ/smU6sLzwX181CCfn1qB3iFSmI7I"
    "hk3djyiMSr1QoESZOa2DVVtbRjL1e+w9HJYi0OsrSzB9ZW9VPvpaImnKImyy3UbPeUAdZb"
    "ES0UYC1D9PYXoucc74WLh8TIZFB7FM+1Qeaazg+j2gZqlFYi62cIGRCba2JYKsKzNdF4od"
    "AZqUJcaomurAAgTTpS85cmnZc2sbICgKwA0J74yf1UAOghQ5suOxwDkfvmIMswBIM20hzU"
    "st15kGEOYgnJ3IitdOE5RCKmzaIRkZltjQIgus3FBLAZO1ra9YJbLhHg6m47s/o0FkVYm3"
    "2ngKeqfvby8/9kySwm"
)
