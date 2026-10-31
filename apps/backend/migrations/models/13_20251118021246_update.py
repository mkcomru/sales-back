from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."wappi_connectors" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "connector_id" VARCHAR(100) NOT NULL UNIQUE,
    "channel_type" VARCHAR(50) NOT NULL,
    "metadata" JSONB NOT NULL,
    "wappi_token" VARCHAR(255),
    "wappi_profile_id" VARCHAR(255),
    "transport_endpoint" VARCHAR(255),
    "enabled" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "backend"."wappi_connectors";"""


MODELS_STATE = (
    "eJztXW1v2zYQ/iuCP3VAV7RZuw3BMMBJ3TZrEmeOsnZrCoGWaVuIRCqUVMcY+t9HUu8SqV"
    "iyZUsLv7QJxaPEh+Tdw7sj8+/AwTNoey9OgQ8XmKwHx9q/AwQcSH8oPXuuDYDrpk9YgQ+m"
    "Nq9shrUsyIvB1PMJMH36ZA5sD9KiGfRMYrm+hREtRYFts0Js0ooWWqRFAbLuA2j4eAH9JS"
    "T0wZevtNhCM/hAG49+de+MuQXtWe6DrRl7Ny83/LXLy86Q/45XZG+bGia2Awelld21v8Qo"
    "qW0hn5UuIIKEdog175OAfT77uqivcY/CL02rhJ+YkZnBOQhsP9PdDTEwMWL40a/xeAcX7C"
    "0/Hr16/cvrX3/6+fWvtAr/kqTkl+9h99K+h4IcgUt98J0/Bz4Ia3AYU9z4/yXkTpeAiKGL"
    "6xfAo59cBC+Gqgq9uCCFL50yO8LPAQ+GDdHCXzLQ3rypQOuv4eT0w3DyjNb6gfUG02kczv"
    "DL6NFR+IxBmkKY/bISkjp8kEzCglhfAK3ATx991tlHO553b2dhe3Yx/MwRddbRk/Px5fu4"
    "egbm0/PxSQFdEtihXtkU10RAISpGFD4Ax60JalZmf7gOBv1BdYXJ3dzGqzqoZmXUbBXjam"
    "LHBWht1DLweaHHDX03oN2FrWcEaX4nNPURKGUY32ECrQX6CNcczTP6UQCZIjMf08K0pe6h"
    "+D2eDHFpSsoIWCXUsTBHaCdp16Af0p/h9enw7WjA0ZwC824FyMyQwRpxZEpbsW0QaAP2xQ"
    "LtehI19O7jJKpUgXDUqE7b7BfMucUb4bUVFMkKfwSDaIy7BoFL8Cww/S1BuApb6RcMbPXg"
    "I5xZNbn1VH7kHDnFEoDAgn81ezd7k2iBVOxc4wX06O41XL+b7WAH+pLgYLHUeCPaHBMtft"
    "+P7IXaBVUsOmb/arFCeDEogNm4EcEu+UvSC9411uevaufc7s45mTf1mEle6ilRk6xW5Lay"
    "FnAZiacEWhWfyyz5bQldpqnu4bgxo8uvLTGlK87CHaDXP5JWRC6zuOoS4VaNfLTPENn3dA"
    "tSYdp5JeWX7qF1VX5p5ZfutF9K+aV3jaiPETTw3PiGLVOw9uXIlgQVwmKEgedZjMz4Rl31"
    "WpbsC8Z7ULT3AbCtuWXyLbrRJBAgb6EvMO97KucRaxLSkregMJeFYmwbmhyuuvpDIHpglA"
    "f6EmrsWzQ81yir19JP1Cyk3c8ICIl3J1QM1b0L6LGN3NxalIH/43p8KQa+JFiA/QbRDn+Z"
    "Wab/XLOpiv/aWiz3t3mAQningWX7FvJesBf+3k6MlyFSvQCKc51hgz1/QXgrvIHiAoh8+Y"
    "aE+8lHoSSoRqH5KJjEMeaYcPeCA33A95B3cF1rRCobUaOz3ehEPTK48hG6eSsshUR+j1kn"
    "V5Px6ej6evR2C9jzNuHNyw1MwpuXUovAHpVhDv1mxAC+DxG3rU0Br26pEfT7j0O2AXnJ/V"
    "4jI8AS2YgmSQCdZp/V0e84yWKnuRFhm/3zuudTI8D9tokRwz/73P89poZ0FQMf2nBBgGNM"
    "8bYJInrU1AnuaDB0I0BWwHUtVgfRnRgmW2LyibV2GjfWM1j2EFeT5s7kFexj8bVtM2fCRr"
    "ZLnNmkDXHeTBpHVGkzg32kzah8XpU0o5KgO5L4sUkStMqY6U/GDNsTCCx6tFWQW/J4N6KS"
    "ZLqmyyptqTQDsMLdk5HpS6BrLzFc6NXNlMnK9AXKvaccIG8FSR1UUwmFqRjTO7heYSJyns"
    "jjHVkZFd7YIryhti+KiTeYoC0fR2yVU5b4WtH9WsErEy+vYpZdW5tVzFKlXytG2VH2E/LD"
    "EBfhDB2hwClZDgHFTJo4dCbatT45u3x/rIVA36LLm4uT0YTVdqaQ3KKT8fh8NLw81qYY2x"
    "CgWzSiVY41SCsUneMHm+4E3gcWgQJ9exJ+tSQrPiNWGIdpi06iuiZo8znPBis350/OipOa"
    "D++zVxxdWskKrXzZ33u4E6YHSN7Ysa9c8fTG0MXJirWgyws9oUmndjhtxRoOc765O/dnlP"
    "Cre7zZTS8N2RK/Pl4/UoQvr6Ga3/eD3R3ksHHcx8khy/4s6lbzUrKoyPwNKWiPeB2MzEDt"
    "1vnwJXwBa/gbsOmA0E5lyjCZ0XoqkaRlF0UIfQk6uY8iEejLznoPu7Zwrm4+/5L6+yPHLw"
    "89BQs5q/V4cVbkKW0oKmhxoii3JCU9zP4tcpLs7OiSyz/mewIjnKGCcgOcvfROOf67tjar"
    "rKpy/Kt7Vzrt/ldO0Z0ZYuVgaeBg2cRFkEa9t/QQ9ArOVl0DlHY4royQsCeP8RFaR9GR3t"
    "EROhmQv12sN9fCbqxqQ1QHk/GNzgK7BAc+C+z+eTM8P3t3xoqi22hY6elQH70fT/42Rp+v"
    "RhP9WEv0EnxwIWl0KUkLB9AxYmfF6zCcjIhiNym7KVnow+z5sidIBWq2cMBUrmtLh1qVxu"
    "2Txk0O39a9RqIgd1BN23A7+OrlJmqS1pLqSf4sryjpMqAT+A4KNoNyNHNCfVGWe9hbM33T"
    "lAnEsnu8SQYEPh6UecDwRh8fa+zhLfo0OvkwHn881lZwusT47hZdjc/PeT6Yi22b4d0E/E"
    "0m8pF8Hh+V7f0S0AVuV3AxiV4oyO0R/dgSlUeg4ZTePYuKBt3woEmggEzJcS1L9vKanla0"
    "RIyNC+g7GmAayylEE70bXZFWRlN+5Cgr06UjR+y1fTpyBBFDoG5ibUZqj3m1CT3rclotga"
    "zXBhDo27f0iW85UGLLcpIFWGeR6Iv4h46SNNqH2RjZ60Fy/450h3t2MbrWhxdXOeDfDvUR"
    "e3KU2+LGpc9+LkzzpBHt05n+QWO/av+ML0fFmZ/U0/9hWWycOhkIrwwwy/D+uDQGJjewgT"
    "trOLB5STWwBx1Y6SVyKpdbZSTXsSM9PnMpu5rr8Tu5Nr+LS7ndOuR2O2zexf/AzaayLlo9"
    "dEkWgQOR6JZK+QYwJ3SoHWBrOO9sr1cj/qP+6rDEsgv5orp0uO2sjMINqwLCUr6DVU5dRL"
    "e/KhbTJxajgoc7ZjX9i7rsEtLdx1uUH/twfuxQvdcOhRfEVEwmj6dL8Nyy6/7RD5GsQja5"
    "5ZYA5LmY+AZEMxdbojQ3ObZiaYWuimepeJYKe6h41lMbWBXPUvGspx7PGkJimcuBwEEUPX"
    "le5RgCaR3lDurY6nxe4Q76BoknjMdUXNKRivTTZ9EKZWZLowaIUfV+AtiOH012WqniL8RK"
    "Tyup2FWT2NXuzcv3/wCUYko+"
)
