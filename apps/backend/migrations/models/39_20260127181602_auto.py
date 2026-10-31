from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "backend"."form_templates" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "api_key_hash" VARCHAR(64) UNIQUE,
    "enabled" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "company_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE,
    "contact_field_id" INT NOT NULL REFERENCES "backend"."fields" ("id") ON DELETE RESTRICT
);
COMMENT ON TABLE "backend"."form_templates" IS 'Form template for web form capture.';
        CREATE TABLE IF NOT EXISTS "backend"."form_submissions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "raw_fields" JSONB NOT NULL,
    "utm_data" JSONB,
    "ip_address" VARCHAR(45),
    "user_agent" VARCHAR(512),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "customer_id" INT REFERENCES "backend"."customers" ("id") ON DELETE SET NULL,
    "form_template_id" INT NOT NULL REFERENCES "backend"."form_templates" ("id") ON DELETE CASCADE,
    "order_id" INT REFERENCES "backend"."orders" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_form_submis_form_te_ceed44" ON "backend"."form_submissions" ("form_template_id", "created_at");
COMMENT ON TABLE "backend"."form_submissions" IS 'Audit table for form submissions.';
        CREATE TABLE IF NOT EXISTS "backend"."form_template_fields" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "position" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "field_id" INT NOT NULL REFERENCES "backend"."fields" ("id") ON DELETE CASCADE,
    "form_template_id" INT NOT NULL REFERENCES "backend"."form_templates" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_form_templa_form_te_4e9b8a" UNIQUE ("form_template_id", "field_id")
);
COMMENT ON TABLE "backend"."form_template_fields" IS 'M:N relationship between FormTemplate and Field.';
        ALTER TABLE "backend"."orders" ADD "utm_data" JSONB;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."orders" DROP COLUMN "utm_data";
        DROP TABLE IF EXISTS "backend"."form_templates";
        DROP TABLE IF EXISTS "backend"."form_submissions";
        DROP TABLE IF EXISTS "backend"."form_template_fields";"""


MODELS_STATE = (
    "eJztXWtzm0jW/itd+pTU62Rzc2ZKtbtVsk0cbWTJa+HJ7EZTLJZaEhvUEC6+7FT++9vd3K"
    "FBgECi5f4wFwOnBU/fTj/n9mdvYyygbr8+U3UVzeEILlbQ6vXBnz2kbiD+H/YDJ6CnmmZ0"
    "m1xw1DudStx5jyp69Oyd7Vjq3MF3l6puQ3xpAe25pZmOZiAiM3AXmgM8CbA0LOA3AgwTWi"
    "p5yn5NWloYc9yUhlZVhFyk/XCh4hgr6Kzp5337A1/W0AI+Qpv8+a03Nzamip4UbUG/RdtA"
    "21E3Zg8/+K3nrC2oLsi9P4ig+V1ZalBfJHDyBOl1xXky6bUhcj7RB8mb3ylzQ3c3KHrYfH"
    "LWBgqf1pBDrq4gIm8PSfOO5RKwkKvrProBft43RY94HxOTWcCl6uoEciKdQTy4GMPTvzTH"
    "sOHewm9j0w9ckV959e7th18+/Pr+44df8SP0TcIrv/z0Pi/6dk+QIjCWez/pfdVRvSco4B"
    "FuYV95OGQwPF+rloTcDQVyiF+N9HAG0GwrKXDxJ6XBDaAsQje4EMEbDeBCfHvy5Fq5vcbd"
    "YZiKa87Q+efBzaXUB3P8PSuYHss52G/URzyN0MpZE8DfFAD92+CG/MKLd29ekrYNPN282T"
    "j277yjt0hfRNirG8P1Bl3JcRsJbB+7rcK75+EbQRatDBnULvCHk9ts6BKCKfQWvuTr4H86"
    "iiVZBSdIf/JXmQLg5OGVNJUHV9fkSza2/UOnCA1kidx5R68+pa6++JgaumEj4OtQ/gzIn+"
    "Dfk7FEETRsZ2XRX4yek//dI++kuo6hIONBURexBTG4GgCT6FYNaY5GwFbunuquQek2Dr0C"
    "Tf81laWrPrCfbAduZmhyLd0M5MlN398fDWuGBhdXw3EfqIuNhrqxJuGNeANZi5IMH3NWpZ"
    "hILcz9AbLHmVQ0c6Tf5cSkCcB6cTX4/WVi4owm48vg8Ri456PJWRrUtYoQ1Au22BxkU3Kc"
    "wJsco6dlxuhp/hg9ZYxRdA8t21M4WIpfAaJZUS5BfXd6Wmbmn57mT31yLzP3Y0p4SZ0kKf"
    "Rc9ZJgSa+GXUqqFngHGIlN63Th8a48cgmZZ4QbOf8uvzNPcv5EzIL4ybCgtkJf4FNGgUoh"
    "55MN51FL3Zu5P4OhEFyN+tJSH0JmILUu4Y/EnwYdb3sYTM8HF1KPOYObw+/Wht3cSspCmF"
    "qeEhhOJRmMb0ejHmMqNwChHDbELXqJJSoHOzKd79T59wfVWiiJeU3uGO+M1JXw2eytzbtN"
    "+oqK1BWFgHwIee1gfGI4V4b11GMQjeG9kyKOce49pUG7FL+Yj+12blAwfrW213zGj/63gs"
    "ocPH/g83SXFOX4m2WQzD8op8R4AXTfp2XL1b11pSyuoYBAlI0ofFQ3ZkVQ4zL7w7XX4wfV"
    "B8P6vtSNhyqoxmXEaM1hywQNIY6ENQZoI0fCfI08BquvI2O11dAVC+qesTsL85nf0KcvN/"
    "5DBQj7jcq4Tb5gTkxeH6+doAhnODdnvwQEpmUs3LmzIwjXXit8wbCPUyudIAUn12ACbT29"
    "evO33Am2J68tw12tAW2EersEv/eK/CC4wguLbJB/g2BByHrM1G2EcUr+Fn4F/TTyzX+Ik3"
    "O7J+dw3FTTTJJSz0k1SVCDZK+sxvFHEs8JtCJ9Ljbld1XoYk11D8fSGl1ybm1n+R1/c9iV"
    "nuZOSUsjF5tcVRXhVjf5tepcQdtW6UTK7vGx28VbPH5Q2XhPltzhh2ih3WsLV9WBLwgeNG"
    "etIaACj8vPbuglZcp4wCbMBXP8/8STSXXSHrAnVL/Evwmt4PuEY2wbm30M3Ax++WR5UqoZ"
    "hqd1JBOE+dt3v5YgzPFTuYQ5vfczfSTKDNkKqOaIt+S50yq8rdgjLEOv7bodyB7aXfJ2Kt"
    "30gWtD4hY5nQ6n8mAs94Fq2xp5c2eGrgbjwSV5yNs98HNJF8v06lxqtH8sM9jTnrGxsf4x"
    "3Re7uNHv33m+58BHJ8u5U2IXzwR8c4bwWindjAcjZTyRpT7AQEILqbqCDAcGfaBIv0mku7"
    "yeUOC97xB6+P7AP+dUdmgNRQRHz+bo8QB2XAbDVW6cR9J7HOkmxMoahjA72K+l8cVwfNkH"
    "/iN4UHuDGZJl50IaDX+TbqSLPsBqpnYPLbiYoU+D4YhcWqqaTv4+H4zPpRG9NCffrOOrdS"
    "ZA8x7dG+ioRMvJdtY/ppNxnhoTyaS66BZh1L4ttLlzAnS8NP/RWof9demiOekjcOdquqMh"
    "+zX52b+3YyIkYBRPk/SMOEmGQZAG0tNEdRx1vibe8Yy5kg9/SqxLPUB+kKsesBxtic99WG"
    "Ws1gUpOdEH9fvAgqZOyPYqKn9chksP/VbOUTFeIINlcfxbUlIEwHUsAM41FzU7NinZQMce"
    "YOIcS79mTMGhwlijY9OyXHYtJ10ZfHbhHMU311UjfBIyzyhO5fDxPcdn/dt/cEWX7Ve50R"
    "VMu583D5uwmx5JbE9iYeqUBdD3NGRZ/yInxALLH31IRKZwaHITkSkiMqXTrLeITGkaUcdA"
    "UDGWyr2hzRlzPx/ZjKBAmI1waEBVqi6vWUleMN7DQvvDVXVtqc29TCJ1QoHyW+AF5n0P5S"
    "RidYLa8lsQmOcFY+k6pPaHyusHQ/TQTibyGgLyLsBYAqzVg+gVgYbAj4Wl1nNbaGWJwWvv"
    "CtrkKLfUVlVsVxlBYbyqb7wKXYxzlL/8bshKin7YoR+sjbI0LEowBO4Jynf4VK1LihoRvb"
    "Nb7/hfpNDlp2pethz5PfoHXd9MzqXpVLrYAfbWM99hmHzvR0V1iJMa2V3rAl7cEpdW92Yg"
    "z5DwZaKCvUTYCkYyyIuT7IsqwZ+ZdN+dVUSLQ2GTeYLq48FntBIzq0GjMeNem/xFIzGRIb"
    "7fzQBS0jrTXUAQwqcSY3c0/HZ4xsK1HWOz+8Dwm+EYiaX6Y9e8CoN/8vz93p67GwKBLsQr"
    "BgZW2xy4MfGH7rqnfsJtyX5THENiWIudV4cJaYNjDDy1vaFxMSWNHcHAcKAOV5a6Ue6MXX"
    "OxyH5TZ0ZHPY/KAUJdZnaFgkPfoQQKD6ppakpTKtZX0hqvelYlN54IQb/MUz5wEwRlA/+r"
    "tL5+FrXYOX6hEL3qfk3Bp+a7N8XA2Obl9KT4fVEyxYH/C0DHUzio1vUa4J4KS3eZ0AJ+2+"
    "DF2/7bMA+RvdbMl9kECI20KFyt9u5qlTuHc8GLSezPH/fNoRHsZITGITwqjjZEozPZRnlY"
    "UioQ41nlokRe0kBzqOaM3UW0y/phV85J2oRzdW4KxSSfvF392C2BotfIbvkTy7TBTp8YjR"
    "2RPXEfKkdnFto97JYid2JH9ieRC3uHfUckTuQocWLM8pm/sweG0e07e2iMbTaE6lvP9V8h"
    "mI9i32153+UrOVzvXoMP3ghJKZCTr2OS/M14QDBVOZeVGu63ofSVXIg1d/BMTCJ7x1FQCB"
    "SYbnIIfGhpCVoNbwfVcItJPCfQClTbYEvdUTfjz2sqrZvFhsZ2jVYcCFopjuO7wXq1Q3d3"
    "cazqCdshA2EyCWOUinwHL7Zk+nM+oSBhpSuElZl9eu50FAsKgaIbqyZgGBkrfpGwtY2r02"
    "LDNh7gu68b06C9qdccX4tzu4WUQncVJlEQ82Upogni/jPb2f9bpOG3W4BQDtBGAUnzqM4x"
    "RMCGpko6B8Scrf6SdK/xeH87axdotPUZPk++Av/x4fubjLvjP33wFQLLRX7QaOxXXB2CF4"
    "Gr2SvvwgmgTkb+Xy9xiwAMXGeND6Mq+P3VFFr32hy+wgoG+D/8d/gGr4YLsMaHJLwqvk68"
    "wycCKn6JwIuZvIpN3kWzyHkYv9EC/6gN0QJfNYDhWmBwPUz+7hlULSxpf1ceHx/xU98hAi"
    "/Cnx6YGn4d4Y5xMNuI3w9Vo7hSclwWnHhThmjBT+UnSn2ToVooAkwgu5iFnwlnT5ZG0uXN"
    "4Irk4ffWlxn6Ori+Hva99WWGzm+n8gTf94IkOkJyrVU8JnUlvwdyhnJKjpeEDG2HfC40G2"
    "9iT5WzL6Tl+MSzlcQKgWaUVTANQ4cqYgMak0phedeiUStcepsOAz+bTEYJevVsmE4Hcnt1"
    "JuGVl0KLH9I8NiDL4VXPUNHN1BS8VReAiCBQdRzHpMQ4Ti618M7AgwIqD/hLjAd8EsWvwQ"
    "qYyFVpC1rYH1f94fTQii4DUqygWCRI6Tt8CgOVKm1n2xrao4nyz7ja/bNP/rzHZzYvqRS+"
    "ssMSso+0Qk9oruxYvyfZxB6h1xaeQTpdu/FiRCpT4ZukXNVQHg5GpFCV5miqPkNng/Mvn4"
    "YjfIkQKEtN10m9Hvn88+01qdbjzNeuia9Mrq5Hkkwr+BgkL5iTrfNTR8V+X0YlfJ+vEr7P"
    "qIQB/FY9YzJDXOSWP3Buedon4bCr26npBkS3dqFbTcsgbVZKVJURFHryLsmphN/NUfrdiJ"
    "iso+jY7sZkce8aJJxcWnFyUU0tJ/dkrfxMnvWNL2j3Y6L2kSkyVEfglTBXK/Ge2262HlwP"
    "AX6ahpp5RhbwwkX+a7+MLMEMm3R5UWJw/uI9uVGdPjHR/tVS0cLY/B288Gl8uAAGiabHah"
    "jVSfD7EbvyFDeAb6k2sNfqu9OPYK3aa/qTNpy7luY8CYvuYSy6hJ4inVGF44rL8GjJ/fih"
    "BNPx8UMu00FuCYa7VUuNOAkdg8LMikAociAp0JkL/Ueer9Ycc4LbWW/mMjlUVnNOjpROxT"
    "4GyT1ZamIs8WeBfhjPMloij1Lgh2daxlLTIXjQnDX44Wr/AyqyH3A7+L/UHTG0C4Eg3Twj"
    "h9KureXGWfp9JUIt96T05QYz5et8+dFMjZnRONP59loF8ND56lux8Frwv3iprqw2x8X2qD"
    "ez19iOKc4eNsS+j3VIm1VcMX+AsmTFYE0n+A4W1AywBV5kWVFhJqtvJtNVtFri/aggAie/"
    "L5jCojfq9wbR8Kp0QPC8wLw+5shgZs/OrycYCnCynhcxHq1UDxR803HyTcLyfhQdKyzvwv"
    "LOl+WdVkCx3buN1kSUOKmBMg0b6/KWLYqgiPIWeSi0ya2TmlEMWt0vJZXPqAfVqppNHygI"
    "7HYJ7KBkcRV6Ky4jgkxjxeqhHaw1ZY+TcRleoNz3kdIziVVBNZIQmLIx/Q6fHrAKUYnwi8"
    "t0iXPirnK2OHGJE1cTauBJoyeuVnXKjL6WLs9ZoFeGph6hWXZtbhZplnu16guNUmiUVTVK"
    "DxfmCN0eEJ9q4tCZo6byzXB82Qce0DPkuTmQpzd3JDk6cYyQBuM+uPP8QWZIwo/0AcQP9L"
    "oy3C34w9WsGl4skZjwYulQLqmj9F7R4T1k1EUpt2qEwntMoDGP+cOmvVppNjmyTgQPzdDk"
    "5oIWXQi44cPnl9NsxX6yHbipuC4k5MTCkDqE+hxexVNoUqrWMfQAq0LDKY7EAb42dKZlLN"
    "y5Uw26pNAzGnSC+miS+mAtf03gF2uqc6OwNH7JhX07gP6cbAC/66glbuFLrlD1fR0Ms4EC"
    "GhT3iRk8xM+kTsc3OiqGdGlY5J9NA34fcix5IKeoUGeYIAlirgN9XWDC7ZcjdFqnrSfBu7"
    "LJ62iibaGwldjkbrrE4jLouHtVxx2CPyp2zTvKiVDAlvluD/oMdPkcSyjAC027B3YlpB1K"
    "jr/w+f0dqN4cegjGdgP6VKUJGxd5TofQgqNUuFDuqMhyuHum9dj46OiU/TjptcvaizN+vQ"
    "XbMcOjuERmKHehOV7JIJpvibQCYq0wEkKVkdhumf6W0vr8EP8oXOYPsZc3vJeHk6KSg1RS"
    "6lAuUq2ZYltxhnKdjUK6oQrOcZkGUO5UUF4rIGsmiQdiZyTO10+TUlxaAD+UUVE/5GuoHz"
    "IKKs3egTcpxKC+tuT8CKW4hPL07bsSWOKn8isdkXsiWvQIgwopMOwcD9VsZEmpZ2Tpyef4"
    "qp3uGKLP6ZSXrbRbCb64yDMafEVn4/iAauKMzC0Nf5I+KjOmWgm7Y8wZZ1e7Y6ypzg3L0n"
    "bH5IqfAHAqyWB8Oxr1stO6Afj4qyOexi6+WuUAdzi2JpzkOVxNfBHYwtQEk6wkT0NaB4EM"
    "5V0e4J3HvcxV03EtmGVqSsqIKAIRRcCfTcVPgF85OXlarpFjq8hPLvKTCwbgGTAAIl/UUX"
    "SsyBfVpN+479JW3WzPEn1OMApP6NY8oeMjS3hB5E22BJA3Eom3PJfLOfUeLndZhzBOjDnh"
    "wLovB9YMNlvomBDAkpxMrAe3MzNX/TGw/P6015oJ7qDzACEC8TeglS/oa2RpmjoNsP1lmb"
    "S28JFtm83BqqjGTmiQH/wVE3mWTp7ihHwUB6nsCVl47wrzeGdOUcLQ26yhVxynIgDzjlEH"
    "dir3LMAMhTg0DecrwVH65e1qL23uLwuo6gAiR3OesA5r4m2E/IFWQAV3rq0haNsYPRXZKk"
    "1vmFV+6zfDVIFjtIlnSPZSBWV04G9pG/1cN2zf75yEmSX5BjycV+GibBn/gyglIlTqhlXq"
    "ROeVRzAt9py2QVF7rknzcjTNKxhEIyGRmIfltphHjOUHRaTlupShl7eqUCIoZR9BKUhzNF"
    "VX5msVobyUajnbf1aUy/X4tEyutNP8XGmnmVxpGG/ymkwst6eni6QPC2fv62TcBw8GmqHR"
    "ZCr3AdYfnbRCXAbgt2UAfpsP8NsMwIKNO1I2TvirHEXHZv1VwrNn1fkaF2ygVzu1o3epE4"
    "PPLpyeqm1rKwQrEr4pqWcU0yNctpqB7mBxjEcAXoIMLIdcXOQZzdYi97aDRIx12JxQFDKW"
    "4+EmHAR3cBAM9tDm8Lu1OY+8S6kVJaIW6brWAIJT0k4Fu2p3MYyv9JWjF0V12GIHS91YNV"
    "EbdmSs+Frrkl6mey0P26GR0LrRnIyLPLu5P2a2mM6VYISWyLs2d7R7Yu7GIjQ0lzYACPe7"
    "gjb19sRb2gZiVBgp2CoKl8nGFo+7FlnYWjRt06/PIFeOyg5kD12YiZZTUc5vpIEsXfhlVR"
    "R/1MzQVB5cSsr558H4UiLFm8iW6I3NGRpMp8PLsRTdDrWO4IlPQ2l0Ed72UArunU+urqSx"
    "3A+Gdx32vPlSLlWNag0a1A63S+3NoiZsE0dBYTPITxd3SEUOKiHzjKiUQ6eA4pS3K2Cg9p"
    "1xp0PniZOyKXfYzAmdgoI3iXiT+JrUqZRFQREaxqkmVp8m/1DjF4ARZYq5O2SIBEM7e4DG"
    "3yyDZH6l4pQYL4AW6ZWtFCt28PvcuX7+s7Inp6SUcAbd4VSlikqZTdkyVVF1r3LVvVJWkB"
    "x38cpl47iCs1WiG6t9GzNPISR3tumD+BmhDnKnDtIk/couzHOyhWa0mpqo9m4mtzKp5m0Z"
    "WBOwZuift4PR8NOQXPrhqrqGvw9fPR/I0uXk5l+K9Pu1dEM442Bdgo8mtGpxx827tpOsPM"
    "yyC/kaZkxEaJeRdpnZoQ9z5r6BS6x2rWXjO0SsdTZxv3C1tbwn8UKJHxWLLneL7n8drcoR"
    "3H/8oEtrzfN3CwlpH00ND/4aRp+kJJ9GH06MPKVc3IX57kjNd7T6U6W9ISYhjFAhhg3QBi"
    "VNKB02QcWGRpeSqUy1jaurjmFNYW6NzswzhUqdHTyt2LBKnc6hbRDn2AWwVbS4Mx6BL07d"
    "vxxo02wpgyGg57Ssx1g18RmaIUmdr4HvVQ1I94AX6mKjoZdgrdrAQDBswiSuZ/6Dzlp1gI"
    "0/D9ozRNrFd9A9tGxK04C1Ru49gQcND2PXAepyCef0ty2SASZwgs/1WosSs9CZIzIbtqzC"
    "bnAX4yFRiaOPy3SJoSc/yBVDT475jwytKR/6mEiXkOfONiJU1iNVWUU0/DF0bG71hupHEo"
    "akOJpkMG3CslnJ2avDJxXGiOnUiSURSsc6rqRj7QrOKtRzv2KhOtp+suqcp9bjo4cObYDV"
    "AwR1LyqAEdpSXXxbHsgw1TYjB2QyG0DiQXGOaPAcIdzRdnZHw+CwvG7zMQwFuEwiVjTeAg"
    "R/ycXvlzR63KTo78I8jq13Nn4QqYw0doV5MONiIhOmyGW311x29KBA01xVHLVJQTFuk7DS"
    "9Nt0QSQ68iJnNc3npvLkRVbRkxJZRW3FfrKxVlx9IY7kxIgWNN8RskGC5jvSjhVFWkV10f"
    "1yersGLET1U+oHLJSNJ34mAQsy7omVpW7ODGbUQvz2SRGX6fgPKndGyQCG3oV0fSOdexlO"
    "bm0Izg2E4NwxLOq+AEi//U2WRtLlzeAKaBgUvO5mCc1arRAHjC/QdCj/GQDpOVk42p2mk9"
    "w/C5f8BNho+LOKiuIIH4l2uc150KHMfamIn0vK8ej4+/ZNueN70fk9c4DHM9Tzea+CZkJI"
    "0MaJdbIu2RTI7g9Oqv71skvx4Fae9AG5OUNfpbPPk8mXPniAd2vD+D5D15PRaDi+7APT0H"
    "WCdx3wG88K5ZfxKIi6ylkXUnJ7RD/YJLM9UHNINx8v5Xe6YkN8CM+hUdm4ZiW5NIy0skoE"
    "2GD1Yl0H00BOIBp5Tjpq1bxwcRnhv1efLYWIIMBQxgq50pjUHpnSUD0TRKng0wRRKjpWEK"
    "WCKD1SorRVntDLaM6iCMNc5wXsYJRUfTsveB6PaPIkwcoyXJPScX70C1haxgaowDbhXFtq"
    "c+Af67IE4e7NlUnvnS53HT9kCn/HxnN8026sSAgmhLhkA9/9WoYNfPdrPhtI7mXCoA5Hrx"
    "76aNoOotwRU01C2koKn3ABrz5I06JcjtNWKBSsUTm1uetQeJ/kNSnLAVn09bk8/I3UOqAP"
    "zNDXwVAeji8VUgwBa/qkoMGDqpE4aIWUQyCf5ERPXQ3Gg0uS3Cp4xlOCrBn6PBhfTD596g"
    "M8MxfGcjlD56PJlFgavTKfdYjw92Xmx/v8+fE+65AZfJISAVTFLZMhLgia5DkeUc1hbris"
    "TGL5+ThSYvs78705tOomiNouELV3GrXXKWSxdhl+M+WW+mwrXVzzz4bUSKl8nozw+hy889"
    "rQa63SrZgrrVU9kjchKWpKi4RbgtQVbL3o2LJsvbdDKDXK+jAkn1FKdmHxEMXgu2YuEmXN"
    "RVnzfRvc8vaSBjDkLxghDSBji9yhLrcOFytS6ZSeeHYM9DhTdQL+iDbJFcYp/iQvRWAVMP"
    "BJ37nyWuJrwrYb/EJ4TZZJ2+c7Cwza+AmRMp47u/Fh8+QcQeyIKNoWnIEPUFaDUV2MrEOK"
    "5S//u+4RfqNyi9aePWyYgUrXKDRemxwi0+b2SZMNMrbPIAlh/vZJkvuJ7ZO77XOpWbajVN"
    "1Ek1K8rP17cMDQ1RpoJoQEmFFQykbVGHnU8oEMBXhU7lqBcK3aa7hQTNW2H/CBvgqYDFEx"
    "NuPppWq55iTkhE9OGlPbNaHFzp+8NWtXXFQk7hLxaEdoCBUW7iPt2PBgV503iCVXb+ZIzF"
    "/C+cSMyNYArY9IuvIoR5C0yRJ8VU1TC7My9Rh8QeqJkyLm4IE8q4TBJw2mmvo6uL4e7pZn"
    "KtmESDLFD7Mhkkw1bCgQQVBbEa0UBCXc6A/nRu/tOZVTpqXEROBZEk/TMpaaDisuuCxZgW"
    "wiibxpWI4C0cI0NFa4UkGANFNaoCvyHgmeSdARgmd6bh0r8h6JvEfdccPO5zfbZK8G0NLm"
    "6x6DtfLvnBSxVWr0jHB06djsPCmgg0jSEKaLY77yHBPhk7NoRWUmU6MCiP7jfALYDo9GSs"
    "6zjnFbqtQzz257Y31ac7ttjN+pYD5rfnv5+f+H9ARn"
)
