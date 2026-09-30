import unicodedata
from dataclasses import dataclass

INSPECTION, DIAGNOSIS = "inspection", "diagnosis"
KIND_LABELS = {INSPECTION: "Inspeção sugerida", DIAGNOSIS: "Possível problema: precisa de diagnóstico profissional"}


def normalize(text):
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


@dataclass(frozen=True)
class Cause:
    key: str
    title: str
    explanation: str
    category: str
    kind: str
    checks: str
    ruled_out_terms: tuple = ()
    normal: bool = False

    @property
    def kind_label(self):
        return "Pode ser normal" if self.normal else KIND_LABELS[self.kind]


@dataclass(frozen=True)
class Rule:
    symptoms: tuple
    terms: tuple
    causes: tuple
    questions: tuple = ()


@dataclass(frozen=True)
class RedFlag:
    terms: tuple
    reason: str


def cause(key, title, explanation, category, kind, checks, ruled_out_terms=(), normal=False):
    return Cause(key, title, explanation, category, kind, checks, ruled_out_terms, normal)


C = {
    "brake_pads": cause("brake_pads", "Pastilhas de freio no fim da vida útil",
                        "Chiado metálico ao frear costuma vir do indicador de desgaste ou de pastilha já no limite.",
                        "brakes", INSPECTION, "Medir a espessura das pastilhas e o estado dos discos."),
    "brake_discs": cause("brake_discs", "Discos de freio empenados ou com rebarba",
                         "Discos deformados causam trepidação no pedal ou no volante ao frear.",
                         "brakes", DIAGNOSIS, "Medir o empeno e a espessura dos discos."),
    "loose_parts": cause("loose_parts", "Peças soltas perto das rodas",
                         "Protetores de pó, presilhas ou fixações da pinça soltos podem fazer barulho ao frear ou em buracos.",
                         "brakes", INSPECTION, "Conferir fixações da pinça, protetores e presilhas."),
    "door_water": cause("door_water", "Água acumulada dentro da porta ou da carroceria",
                        "Drenos das portas obstruídos ou vedações ressecadas deixam água parada, que faz barulho de "
                        "líquido ao frear ou em curvas.", "body", INSPECTION,
                        "Verificar os drenos na parte de baixo das portas e as vedações."),
    "fuel_slosh": cause("fuel_slosh", "Movimento do combustível no tanque",
                        "Com o tanque mais cheio, o combustível pode fazer barulho ao frear ou arrancar; costuma ser normal.",
                        "fuel", INSPECTION, "Observar se o ruído muda com o nível do tanque.",
                        ruled_out_terms=("combustivel", "tanque", "bomba"), normal=True),
    "suspension": cause("suspension", "Componentes da suspensão com folga",
                        "Bieletas, buchas, batentes e amortecedores desgastados fazem estalos ou batidas secas em buracos "
                        "e lombadas.", "suspension", DIAGNOSIS,
                        "Verificar folgas em bieletas, buchas, pivôs e o estado dos amortecedores."),
    "exhaust_loose": cause("exhaust_loose", "Escapamento ou protetores soltos",
                           "Suportes de borracha do escapamento ou protetores plásticos soltos batem em irregularidades.",
                           "engine", INSPECTION, "Conferir suportes do escapamento e protetores inferiores."),
    "cv_joint": cause("cv_joint", "Juntas homocinéticas desgastadas",
                      "Estalos ao manobrar com o volante bem esterçado são típicos de junta homocinética gasta ou com a "
                      "coifa rasgada.", "transmission", DIAGNOSIS, "Verificar coifas e folga das juntas homocinéticas."),
    "steering": cause("steering", "Terminais ou caixa de direção",
                      "Folgas na direção causam ruídos em manobras e sensação de volante solto.", "suspension", DIAGNOSIS,
                      "Verificar terminais, axiais e a caixa de direção."),
    "belt": cause("belt", "Correias auxiliares ou tensores",
                  "Chiado ao ligar o motor ou acelerar, principalmente com umidade, costuma vir de correia ressecada ou "
                  "tensor fraco.", "belts", INSPECTION, "Verificar estado e tensão das correias e dos tensores."),
    "wheel_bearing": cause("wheel_bearing", "Rolamento de roda",
                           "Ronco que aumenta com a velocidade e muda em curvas pode indicar rolamento de roda gasto.",
                           "suspension", DIAGNOSIS, "Verificar folga e ruído dos rolamentos de roda."),
    "tire_wear": cause("tire_wear", "Desgaste irregular dos pneus",
                       "Pneus com desgaste irregular fazem ruído de rodagem e vibração; indicam alinhamento, calibragem ou "
                       "suspensão fora do ideal.", "tires", INSPECTION,
                       "Verificar desgaste, calibragem, alinhamento e data de fabricação dos pneus."),
    "wheel_balance": cause("wheel_balance", "Rodas desbalanceadas ou pneu deformado",
                           "Vibração no volante em certas velocidades costuma ser balanceamento ou pneu/roda deformados.",
                           "tires", INSPECTION, "Balancear as rodas e verificar deformações nos pneus e rodas."),
    "engine_mounts": cause("engine_mounts", "Coxins do motor",
                           "Coxins gastos transmitem a vibração do motor para a cabine, principalmente parado ou ao "
                           "engatar marcha.", "engine", DIAGNOSIS, "Verificar o estado dos coxins do motor e do câmbio."),
    "misfire": cause("misfire", "Falha de ignição",
                     "Velas, cabos ou bobinas com defeito causam trancos, motor irregular e perda de força.", "engine",
                     DIAGNOSIS, "Verificar velas, cabos e bobinas e ler os códigos de falha."),
    "engine_check": cause("engine_check", "Falha registrada na central do motor",
                          "A luz de injeção indica que a central registrou uma falha; só a leitura com scanner mostra "
                          "qual.", "fuel", DIAGNOSIS, "Ler os códigos de falha com scanner e explicar o resultado."),
    "fuel_feed": cause("fuel_feed", "Alimentação de combustível",
                       "Bomba, filtro ou pressão de combustível fora do normal causam dificuldade na partida e falhas.",
                       "fuel", DIAGNOSIS, "Medir a pressão de combustível e verificar o filtro.",
                       ruled_out_terms=("bomba", "combustivel")),
    "fuel_quality": cause("fuel_quality", "Combustível de má qualidade",
                          "Se os sintomas começaram depois de um abastecimento, o combustível pode ser a causa.", "fuel",
                          INSPECTION, "Perguntar sobre o último abastecimento e, se necessário, analisar o combustível."),
    "oil_pressure": cause("oil_pressure", "Pressão ou nível de óleo",
                          "A luz do óleo indica pressão baixa. Rodar assim pode danificar o motor.", "engine", DIAGNOSIS,
                          "Conferir o nível de óleo e medir a pressão."),
    "cooling": cause("cooling", "Sistema de arrefecimento",
                     "Nível baixo do líquido, vazamentos, válvula termostática ou ventoinha podem fazer o motor esquentar.",
                     "cooling", DIAGNOSIS, "Verificar nível, vazamentos, ventoinha e válvula termostática."),
    "charging": cause("charging", "Sistema de carga (alternador, correia ou bateria)",
                      "A luz da bateria acesa com o motor ligado indica que a bateria não está sendo carregada.",
                      "electrical", DIAGNOSIS, "Medir a tensão de carga do alternador e testar a bateria."),
    "brake_system": cause("brake_system", "Sistema de freio (fluido, freio de mão ou ABS)",
                          "A luz do freio pode indicar freio de mão acionado, nível baixo de fluido ou falha no ABS.",
                          "brakes", DIAGNOSIS, "Verificar o nível do fluido, pastilhas e o sistema ABS."),
    "airbag": cause("airbag", "Sistema de airbag",
                    "Com a luz do airbag acesa, o airbag pode não funcionar numa colisão.", "electrical", DIAGNOSIS,
                    "Ler os códigos de falha do módulo de airbag."),
    "warning_generic": cause("warning_generic", "Significado da luz no painel",
                             "Consulte no manual o símbolo e a cor. Luz vermelha: pare com segurança. Amarela: agende "
                             "verificação.", "general", INSPECTION, "Identificar o símbolo e ler os códigos de falha."),
    "battery": cause("battery", "Bateria fraca ou terminais oxidados",
                     "Partida lenta, cliques ou painel que apaga ao dar partida costumam ser bateria ou terminais.",
                     "battery", INSPECTION, "Fazer teste de carga da bateria e limpar os terminais."),
    "starter": cause("starter", "Motor de partida ou relé",
                     "Se a bateria está boa e o motor não gira, o motor de partida ou o relé podem estar falhando.",
                     "electrical", DIAGNOSIS, "Testar o motor de partida e o circuito de partida."),
    "flex_cold": cause("flex_cold", "Partida a frio com etanol",
                       "Em motores flex, partidas com mais etanol no tanque em manhãs frias podem demorar mais.", "fuel",
                       INSPECTION, "Verificar se a dificuldade acontece só com etanol e motor frio.", normal=True),
    "tire_pressure": cause("tire_pressure", "Calibragem dos pneus",
                           "Pneus abaixo da pressão indicada aumentam o consumo e o desgaste.", "tires", INSPECTION,
                           "Calibrar conforme a etiqueta do veículo e a carga transportada."),
    "air_filter_plugs": cause("air_filter_plugs", "Filtro de ar e velas",
                              "Filtro de ar saturado ou velas gastas pioram a queima e aumentam o consumo.", "filters",
                              INSPECTION, "Verificar o filtro de ar e as velas."),
    "fuel_mix": cause("fuel_mix", "Proporção de etanol e gasolina",
                      "O etanol rende menos quilômetros por litro que a gasolina; mudar a mistura altera o consumo.",
                      "fuel", INSPECTION, "Comparar o consumo com o mesmo combustível e o mesmo tipo de trajeto.",
                      normal=True),
    "driving_conditions": cause("driving_conditions", "Trânsito e trajetos curtos",
                                "Anda-e-para e trajetos curtos com motor frio aumentam o consumo.", "general",
                                INSPECTION, "Comparar trajetos semelhantes antes de concluir.", normal=True),
    "coolant_leak": cause("coolant_leak", "Vazamento do sistema de arrefecimento",
                          "Líquido verde, rosa ou azulado costuma ser o aditivo do arrefecimento.", "cooling", DIAGNOSIS,
                          "Verificar mangueiras, radiador, reservatório e bomba d'água."),
    "oil_leak": cause("oil_leak", "Vazamento de óleo",
                      "Manchas escuras e oleosas costumam ser óleo do motor.", "engine", DIAGNOSIS,
                      "Localizar o vazamento (juntas, retentores, bujão e filtro)."),
    "fuel_leak": cause("fuel_leak", "Vazamento de combustível",
                       "Líquido com cheiro de combustível sob o carro é um risco de incêndio.", "fuel", DIAGNOSIS,
                       "Localizar o vazamento nas linhas, tanque ou injeção."),
    "brake_fluid_leak": cause("brake_fluid_leak", "Vazamento de fluido de freio",
                              "Líquido oleoso perto das rodas ou do pedal pode ser fluido de freio.", "brakes", DIAGNOSIS,
                              "Verificar flexíveis, pinças, cilindros e o reservatório."),
    "ac_condensation": cause("ac_condensation", "Água do ar-condicionado",
                             "Água limpa e sem cheiro pingando sob o carro com o ar-condicionado ligado é condensação.",
                             "ac", INSPECTION, "Confirmar que é água limpa, sem cheiro e sem cor.", normal=True),
    "water_ingress": cause("water_ingress", "Entrada de água na cabine",
                           "Vedações ressecadas ou drenos obstruídos deixam a água entrar no interior.", "body",
                           INSPECTION, "Verificar vedações, drenos e o dreno do ar-condicionado."),
    "leak_identify": cause("leak_identify", "Identificar o líquido",
                           "Coloque um papelão claro sob o carro parado para ver a cor, o cheiro e o local da mancha.",
                           "general", INSPECTION, "Identificar o líquido pela cor, cheiro e local."),
    "fuses_grounds": cause("fuses_grounds", "Fusíveis, conectores ou aterramento",
                           "Mau contato e aterramentos oxidados causam falhas intermitentes.", "electrical", DIAGNOSIS,
                           "Verificar fusíveis, conectores e pontos de aterramento."),
    "accessories": cause("accessories", "Acessórios instalados (som, alarme, rastreador)",
                         "Instalações adicionais podem consumir bateria com o carro desligado ou causar mau contato.",
                         "audio", INSPECTION, "Medir o consumo com o carro desligado e revisar a instalação."),
    "body_wear": cause("body_wear", "Desgaste de pintura, plásticos ou borrachas",
                       "Sol e chuva ressecam plásticos e borrachas e desgastam o verniz.", "body", INSPECTION,
                       "Avaliar se é estético ou se afeta vedação e fixação."),
    "generic": cause("generic", "Origem a identificar",
                     "Anote quando acontece (ao frear, em curvas, em buracos, parado, frio ou quente) para ajudar o "
                     "mecânico a localizar.", "general", INSPECTION, "Reproduzir o sintoma com o mecânico."),
}


def pick(*keys):
    return tuple(C[key] for key in keys)


BRAKE_TERMS = ("frear", "freio", "frenag", "freand", "freada")

RULES = [
    Rule(("noise",), ("liquido", "agua", "chacoalh", "balanc", "sacode"), pick("door_water", "fuel_slosh"),
         ("Pode verificar os drenos das portas e se há água acumulada?", "O ruído muda com o nível do tanque?")),
    Rule(("noise",), BRAKE_TERMS, pick("brake_pads", "brake_discs", "loose_parts"),
         ("Qual a espessura restante das pastilhas e o estado dos discos?",
          "O ruído vem das rodas dianteiras ou traseiras?")),
    Rule(("noise",), ("buraco", "lombada", "irregular", "paralelep", "estalo", "batida", "trepid"),
         pick("suspension", "exhaust_loose"),
         ("Quais peças da suspensão têm folga?", "Os amortecedores têm vazamento?")),
    Rule(("noise",), ("curva", "virar", "manobra", "esterc", "volante"), pick("cv_joint", "steering"),
         ("As coifas das juntas homocinéticas estão inteiras?",)),
    Rule(("noise",), ("chiado", "assobio", "ligar", "acelera", "correia", "motor"), pick("belt"),
         ("As correias e os tensores estão em bom estado?",)),
    Rule(("noise",), ("roda", "zumbido", "ronco", "velocidade", "rodagem"), pick("wheel_bearing", "tire_wear"),
         ("O ruído muda em curvas para um lado ou outro?",)),
    Rule(("vibration",), BRAKE_TERMS, pick("brake_discs"), ("Os discos estão empenados?",)),
    Rule(("vibration",), ("volante", "velocidade", "km/h", "estrada", "rodovia"), pick("wheel_balance", "tire_wear"),
         ("Em que velocidade a vibração aparece?",)),
    Rule(("vibration",), ("parado", "marcha lenta", "semaforo", "ligado", "engat"), pick("engine_mounts", "misfire"),
         ("Há falha de ignição registrada na central?",)),
    Rule(("warning_light",), ("oleo",), pick("oil_pressure"), ("Qual o nível e a pressão do óleo?",)),
    Rule(("warning_light",), ("temperatura", "arrefec", "agua", "radiador"), pick("cooling"),
         ("Há vazamento ou a ventoinha está funcionando?",)),
    Rule(("warning_light",), ("bateria", "carga", "alternador"), pick("charging", "battery"),
         ("Qual a tensão de carga do alternador?",)),
    Rule(("warning_light",), ("freio", "abs"), pick("brake_system"), ("O nível do fluido de freio está correto?",)),
    Rule(("warning_light",), ("injecao", "motor", "check", "amarela", "laranja"), pick("engine_check"),
         ("Quais códigos de falha o scanner mostrou e o que significam?",)),
    Rule(("warning_light",), ("airbag",), pick("airbag"), ("Qual o código de falha do airbag?",)),
    Rule(("starting",), ("clique", "estalo", "nao gira", "luzes fracas", "painel apaga", "fraca"), pick("battery", "starter"),
         ("Qual o resultado do teste de carga da bateria?",)),
    Rule(("starting",), ("frio", "manha", "etanol", "alcool"), pick("flex_cold", "battery"),
         ("A dificuldade acontece só com o motor frio?",)),
    Rule(("malfunction",), ("engasg", "falha", "tranco", "forca", "potencia", "morre", "apaga", "irregular"),
         pick("misfire", "engine_check", "fuel_feed", "fuel_quality"),
         ("Há códigos de falha registrados?", "Os sintomas começaram depois de algum abastecimento?")),
    Rule(("leak",), ("verde", "rosa", "azul", "arrefec", "radiador", "reservatorio"), pick("coolant_leak"),
         ("De onde vem o vazamento do arrefecimento?",)),
    Rule(("leak",), ("oleo", "preto", "marrom", "escuro"), pick("oil_leak"), ("Qual junta ou retentor está vazando?",)),
    Rule(("leak",), ("gasolina", "combustivel", "etanol", "alcool"), pick("fuel_leak"),
         ("Onde está o vazamento de combustível?",)),
    Rule(("leak",), ("fluido de freio", "perto da roda", "pedal"), pick("brake_fluid_leak"),
         ("O nível do fluido de freio baixou?",)),
    Rule(("leak",), ("ar condicionado", "ar-condicionado", "transparente", "sem cheiro", "agua"),
         pick("ac_condensation", "water_ingress"), ()),
    Rule(("leak",), ("dentro", "interior", "tapete", "molhad", "porta"), pick("water_ingress"),
         ("Por onde a água está entrando?",)),
    Rule(("electrical",), ("som", "radio", "alto-falante", "alto falante", "modulo", "alarme", "rastreador"),
         pick("accessories"), ("A instalação dos acessórios está correta e protegida por fusível?",)),
    Rule(("wear",), ("pneu",), pick("tire_wear"), ("O desgaste indica problema de alinhamento ou suspensão?",)),
]

GENERIC = {
    "noise": pick("generic"),
    "vibration": pick("wheel_balance", "suspension"),
    "warning_light": pick("warning_generic"),
    "starting": pick("battery", "starter", "fuel_feed"),
    "consumption": pick("tire_pressure", "air_filter_plugs", "fuel_mix", "driving_conditions", "engine_check"),
    "malfunction": pick("misfire", "engine_check", "fuel_feed"),
    "leak": pick("leak_identify"),
    "electrical": pick("battery", "charging", "fuses_grounds", "accessories"),
    "wear": pick("body_wear", "tire_wear"),
    "other": pick("generic"),
}
GENERIC_QUESTIONS = {
    "consumption": ("Há códigos de falha registrados?",
                    "Como medir o consumo: encha o tanque, zere o hodômetro parcial e anote os km até o próximo abastecimento."),
    "warning_light": ("Qual é o símbolo e a cor da luz? Ela fica acesa ou pisca?",),
}

RED_FLAGS = [
    RedFlag(("pedal baixo", "pedal fundo", "pedal mole", "pedal esponj", "nao freia", "perdeu o freio", "freio falhou"),
            "O relato envolve a eficiência do freio."),
    RedFlag(("fumaca", "fogo", "cheiro de queimado", "queimando"), "Há fumaça ou cheiro de queimado."),
    RedFlag(("cheiro de gasolina", "cheiro de combustivel", "vazando gasolina", "vazamento de combustivel",
             "pingando gasolina"), "Possível vazamento ou cheiro de combustível."),
    RedFlag(("superaquec", "temperatura alta", "ferveu", "fervendo", "ponteiro da temperatura"),
            "Há sinal de superaquecimento do motor."),
    RedFlag(("direcao travou", "volante travou", "perdeu a direcao", "direcao pesou de repente"),
            "Houve alteração repentina na direção."),
    RedFlag(("luz vermelha",), "Luz de advertência vermelha no painel."),
    RedFlag(("luz do oleo", "pressao do oleo"), "Luz de pressão do óleo acesa."),
    RedFlag(("fluido de freio",), "Possível vazamento de fluido de freio."),
]

SAFETY_CATEGORIES = {"brakes", "suspension", "tires"}
GENERAL_QUESTIONS = (
    "O que foi verificado e quais medidas ou códigos de falha foram encontrados?",
    "O conserto é urgente ou pode esperar? Por quê?",
    "Qual a garantia das peças e da mão de obra?",
    "Pode me mostrar as peças substituídas?",
)
