import random
import hashlib
from datetime import datetime, timedelta, date, timezone


class FakerBR:
    """Faker com locale pt_BR embutido."""

    def __init__(self, seed=None):
        self._rng = random.Random(seed)
        self.reseed = self._rng.seed

        self._primeiros = [
            "Ana","Bruno","Carla","Diego","Dominic","Elena","Felipe","Gabriela","Henrique","Rahqueel",
            "Isabel","João","Joemetric","Karen","Lucas","Mariana","Nicolas","Olivia","Pedro",
            "Quézia","Rafael","Sabrina","Thiago","Ursula","Victor","Wanda","Xavier",
            "Yasmin","Zélia","André","Beatriz","Caio","Denise","Eduardo","Fernanda",
            "Gustavo","Helena","Igor","Juliana","Larissa","Marcelo","Natália",
            "Oswaldo","Patrícia","Roberto","Sônia","Túlio","Vanessa","Wellington","Ximena",
            "Adriana","Bento","Cecília","Davi","Elisa","Fabiano","Giovanna","Humberto",
            "Ingrid","José","Karina","Leandro","Mônica","Nilo","Paulo","Pornelius","Roberta",
            "Sérgio","Tatiane","Ulisses","Yago","Zilá","Renata","Rodrigo","Camila",
            "Márcio","Priscila","Danilo","Letícia","Alexandre","Bianca","Cláudio","Débora","Laura",
        ]
        self._sobrenomes = [
            "Lima","Costa","Mendes","Welker","Ferreira","Souza","Santos","Rocha","Alves","Hubertison","Desh"
            "Castro","Pereira","Nunes","Gomes","Oliveira","Barbosa","Martins","Cardoso",
            "Ramos","Torres","Pinto","Moreira","Freitas","Hugo","Correia","Azevedo",
            "Borges","Melo","Cunha","Ribeiro","Lil","Santana","Wada","Araújo","Lopes","Dias","Nascimento",
            "Vasconcelos","Teixeira","Campos","Vale","Werner","Figueiredo","Duarte","Silveira","Jabá",
            "Braga","Cavalcante","Esteves","Guimarães","Fontes","Coelho","Machado",
            "Prado","Rezende","Bastos","Leite","Carvalho","Vieira","Andrade","Monteiro",
            "Queiroz","Macedo","Saraiva","Paiva","Rodrigues","Batista","Xavier","Nogueira",
            "Pacheco","Vargas","Lacerda","Faria","Tavares","Medeiros","Brandão","Muniz",
            "Barreto","Albuquerque","Ferraz","Dantas","Moura","Paixão","Deus","Cruz",
        ]
        self._dominios = [
            "gmail.com","hotmail.com","institutojef.org.br","yahoo.com.br","outlook.com",
            "uol.com.br","bol.com.br","terra.com.br","ig.com.br","jfsa.com.br"
        ]
        self._estados_cidades = [
            ("SP","São Paulo",    -23.5505,-46.6333),
            ("SP","Campinas",     -22.9056,-47.0608),
            ("SP","Caieiras",     -23.3643,-46.7412),
            ("SP","Guarulhos",    -23.4628,-46.5328),
            ("SP","Santo André",  -23.6639,-46.5282),
            ("SP","Osasco",       -23.5324,-46.7918),
            ("SP","São Bernardo", -23.6944,-46.5652),
            ("SP","Ribeirão Preto",-21.1791,-47.8069),
            ("RJ","Rio de Janeiro",-22.9068,-43.1729),
            ("MG","Belo Horizonte",-19.9191,-43.9386),
            ("PR","Curitiba",     -25.4284,-49.2733),
            ("RS","Porto Alegre", -30.0346,-51.2177),
            ("BA","Salvador",     -12.9714,-38.5014),
            ("CE","Fortaleza",    -3.7172, -38.5433),
            ("AM","Manaus",       -3.1190, -60.0217),
        ]
        self._logradouros = [
            "Rua das Flores","Avenida Paulista","Rua XV de Novembro",
            "Alameda Santos","Rua Augusta","Avenida Brasil","Rua Consolação",
            "Avenida das Nações","Rua do Comércio","Travessa da Paz",
            "Rua Harmonia","Avenida Liberdade","Rua Vergueiro","Avenida Jabaquara",
            "Rua dos Pinheiros","Avenida Marcelino Bressiani","Alameda Campinas","Rua Haddock Lobo",
            "Avenida Rebouças","Rua Teodoro Sampaio","Rua Boa Vista",
            "Rua da Consolação","Avenida Ibirapuera","Rua Funchal",
            "Avenida Faria Lima","Rua Itapeva","Rua Bela Cintra",
        ]
        self._complementos = [
            "Apto 12","Apto 34","Sala 201","Conjunto 5","Bloco B Apto 8",
            "Casa 2","Loja 3","Cobertura","Terreo","Fundos",None,None,None,
        ]

    # == primitivos =========== 
    def _r(self): return self._rng

    def first_name(self):
        return self._r().choice(self._primeiros)

    def last_name(self):
        return self._r().choice(self._sobrenomes)

    def name(self):
        return f"{self.first_name()} {self.last_name()}"

    def email(self, nome=None):
        n = (nome or self.name()).lower()
        n = n.replace(" ",".")
        for c in "áàãâéêíóôõúüçñ":
            posb = {"á":"a","à":"a","ã":"a","â":"a","é":"e","ê":"e",
                    "í":"i","ó":"o","ô":"o","õ":"o","ú":"u","ü":"u",
                    "ç":"c","ñ":"n"}
            n = n.replace(c, posb.get(c,c))
        sufixo = self._r().randint(1, 999)
        dom = self._r().choice(self._dominios)
        return f"{n}{sufixo}@{dom}"

    def password(self, email="x"):
        return "$2b$12$" + hashlib.sha256(email.encode()).hexdigest()[:53]

    def cpf(self):
        """11 dígitos sem máscara -- tb_usuarios.cpf é VARCHAR(11) no schema."""
        d = [self._r().randint(0, 9) for _ in range(11)]
        return "".join(str(x) for x in d)

    def cnpj(self):
        d = [self._r().randint(0,9) for _ in range(14)]
        return (f"{d[0]}{d[1]}.{d[2]}{d[3]}{d[4]}.{d[5]}{d[6]}{d[7]}"
                f"/{d[8]}{d[9]}{d[10]}{d[11]}-{d[12]}{d[13]}")

    def phone(self):
        ddd = self._r().choice([11,21,31,41,51,61,71,81,91,85,92,48,62,27])
        num = self._r().randint(90000000, 99999999)
        return f"({ddd}) 9{num}"

    def cep(self):
        return f"{self._r().randint(10000,99999)}-{self._r().randint(100,999)}"

    def state(self):
        return self._r().choice(self._estados_cidades)[0]

    def city(self):
        return self._r().choice(self._estados_cidades)[1]

    def street_name(self):
        return self._r().choice(self._logradouros)

    def building_number(self):
        return str(self._r().randint(1, 3500))

    def secondary_address(self):
        return self._r().choice(self._complementos)

    def address_tuple(self):
        """Retorna (uf, cidade, cep, logradouro, numero) -- colunas de tb_enderecos."""
        uf, cidade, _lat_base, _lng_base = self._r().choice(self._estados_cidades)
        return (
            uf, cidade,
            self.cep(),
            self.street_name(),
            self.building_number(),
        )

    def date_of_birth(self, min_age=18, max_age=70):
        today = date.today()
        age = self._r().randint(min_age, max_age)
        days = self._r().randint(0, 364)
        return today - timedelta(days=age*365 + days)

    def date_time_between(self, start_days_ago=730, end_days_ago=0):
        """Retorna datetime UTC aleatório entre dois pontos no passado."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=start_days_ago)
        end   = now - timedelta(days=end_days_ago)
        delta = (end - start).total_seconds()
        return start + timedelta(seconds=self._r().random() * delta)

    def date_time_growth(self, start_days_ago=730, end_days_ago=0, power=2.5):
        """
        Como date_time_between, mas enviesado para o fim do intervalo (mais
        perto de hoje) -- usa r = random()**(1/power), que concentra a massa
        próximo de 1. Serve para simular crescimento ao longo do tempo
        (mais usuários/postagens recentes que antigos) em vez de ruído
        uniforme, o que fica mais legível em gráficos de série temporal.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=start_days_ago)
        end   = now - timedelta(days=end_days_ago)
        delta = (end - start).total_seconds()
        r = self._r().random() ** (1.0 / power)
        return start + timedelta(seconds=r * delta)

    def date_time_future(self, max_days=90):
        now = datetime.now(timezone.utc)
        return now + timedelta(days=self._r().randint(1, max_days),
                               hours=self._r().randint(0,23))

    def boolean(self, chance_of_getting_true=80):
        return self._r().randint(1, 100) <= chance_of_getting_true

    def random_element(self, elements):
        return self._r().choice(list(elements))

    def random_elements(self, elements, length=3, unique=True):
        lst = list(elements)
        k = min(length, len(lst))
        if unique:
            return self._r().sample(lst, k)
        return [self._r().choice(lst) for _ in range(k)]

    def random_int(self, min=0, max=100):
        return self._r().randint(min, max)

    def sentence(self, nb_words=8):
        words = ["reciclagem","sustentável","ambiental","coleta","resíduo",
                 "material","consciente","descarte","orgânico","cooperativa",
                 "condomínio","morador","pontuação","engajamento","ecológico"]
        return " ".join(self._r().choice(words) for _ in range(nb_words)).capitalize() + "."

    def company(self):
        tipos = ["Cooperativa","EcoColeta","ReciclaCity","GreenColect","CoopVerde",
                 "EcoSol","Reciclar","CoopAmb","LimpaCity","EcoNet","Recicla Mais",
                 "Verde Vida","EcoPonto","Recicla Brasil","Coleta Verde","EcoAção",
                 "Sustenta","BioColeta","Renova Verde","Planeta Limpo"]
        return f"{self._r().choice(tipos)} {self.last_name()}"

    def condominio_name(self):
        padroes = [
            "Residencial {}", "Condomínio {}", "Villa {}", "Recanto {}",
            "Parque {}", "Jardim {}", "Bosque {}", "Vila {}", "Spazio {}",
            "Mirante {}", "Portal {}", "Solar {}",
        ]
        temas = [
            "das Flores", "do Sol", "Verde", "dos Ipês", "das Palmeiras",
            "Águas Claras", "Bela Vista", "Monte Alegre", "Vale Verde",
            "das Acácias", "do Bosque", "Jequitibá", "das Araucárias",
            "Colina Verde", "Costa Azul", "Serra Azul", "Boa Vista",
            "Nova Esperança", "das Cerejeiras", "Alto da Serra",
        ]
        return self._r().choice(padroes).format(self._r().choice(temas))

    def edificio_comercial_name(self):
        padroes = [
            "Edifício {}", "Business Center {}", "Corporate {}", "Torre {}",
            "Ed. Comercial {}", "Centro Empresarial {}",
        ]
        temas = [
            "Paulista", "Faria Lima", "Berrini", "Alphaville", "Atlântico",
            "Millennium", "Prime", "Executive", "Horizonte", "Global",
            "Trade Center", "Pinheiros", "Ibirapuera", "Nações Unidas",
            "Panamérica",
        ]
        return self._r().choice(padroes).format(self._r().choice(temas))

    def url(self, path="fotos", ext="jpg"):
        uid = self._r().randint(10000, 99999)
        return f"https://storage.ecociente.com.br/{path}/{uid}.{ext}"

    def codigo_acesso(self, seq):
        return f"ECO{seq:04d}"
