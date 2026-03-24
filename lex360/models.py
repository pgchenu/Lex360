"""Modèles Pydantic pour les réponses de l'API Lexis 360."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Utilitaires ---

def ms_to_datetime(ms: int | None) -> datetime | None:
    """Convertit un timestamp en millisecondes en datetime."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000)


# --- Utilisateur ---

class UserProfile(BaseModel):
    """Profil utilisateur retourné par /api/user/whoami."""
    model_config = ConfigDict(extra="allow")


# --- Documents : métadonnées ---

class DocumentInfo(BaseModel):
    """Informations du document (clé 'document' dans les metadata)."""
    model_config = ConfigDict(extra="allow")

    id: str = ""
    kid: str = ""
    title: str = ""
    type: str = ""
    date: int | None = None
    doc_id_stable: str = Field(default="", alias="docIdStable")
    type_contenu: str = Field(default="", alias="typeContenu")
    combining_id: str | None = Field(default=None, alias="combiningId")
    thematique: str = ""
    creation_date: int | None = Field(default=None, alias="creationDate")
    commented_by: int | None = Field(default=None, alias="commentedBy")
    nb_dec_similaire: int | None = Field(default=None, alias="nbDecSimilaire")
    code_publication: str | None = Field(default=None, alias="codePublication")
    signatures: list[str] = Field(default_factory=list)
    type_contribution: str | None = Field(default=None, alias="typeContribution")
    ror: list[str] = Field(default_factory=list)

    @property
    def date_dt(self) -> datetime | None:
        return ms_to_datetime(self.date)


class JurisprudenceInfo(BaseModel):
    """Informations jurisprudence (clé 'jurisprudence')."""
    model_config = ConfigDict(extra="allow")

    annee: int | None = None
    classe_juridiction: str = Field(default="", alias="classeJuridiction")
    classe_juridiction_short: str = Field(default="", alias="classeJuridictionShort")
    date_de_decision: int | None = Field(default=None, alias="dateDeDecision")
    numero_jurisprudence: list[str] = Field(default_factory=list, alias="numeroJurisprudence")
    solution_juridique: str = Field(default="", alias="solutionJuridique")
    solution_juridique_label: str = Field(default="", alias="solutionJuridiqueLabel")
    code_publications: list[str] = Field(default_factory=list, alias="codePublications")
    type_formation: str = Field(default="", alias="typeFormation")
    type_formation_code: str = Field(default="", alias="typeFormationCode")
    type_decision: str = Field(default="", alias="typeDecision")
    type_jp: str = Field(default="", alias="typeJp")
    type_litiges: list[str] = Field(default_factory=list, alias="typeLitiges")
    themes: list[str] = Field(default_factory=list)
    crit_selection: list[str] = Field(default_factory=list, alias="critSelection")
    legi_ref: dict[str, Any] | None = Field(default=None, alias="legiRef")

    @property
    def date_decision_dt(self) -> datetime | None:
        return ms_to_datetime(self.date_de_decision)


class EncycloInfo(BaseModel):
    """Informations encyclopédie (clé 'encyclo')."""
    model_config = ConfigDict(extra="allow")

    type: str = ""
    code_publication: str = Field(default="", alias="codePublication")
    code_publication_label: str = Field(default="", alias="codePublicationLabel")
    matricule: str = ""
    auteur: list[str] = Field(default_factory=list)
    type_contribution: str = Field(default="", alias="typeContribution")


class RevueInfo(BaseModel):
    """Informations revue (clé 'revue')."""
    model_config = ConfigDict(extra="allow")

    date: int | None = None
    matiere_code: str = Field(default="", alias="matiereCode")
    matricule: int | None = None
    numero: list[int] = Field(default_factory=list)
    numero_label: str = Field(default="", alias="numeroLabel")
    sommaire_id: str = Field(default="", alias="sommaireId")
    type_contribution_code: str = Field(default="", alias="typeContributionCode")
    type_contribution_label: str = Field(default="", alias="typeContributionLabel")
    matiere: str = ""
    has_pdf: bool = Field(default=False, alias="hasPdf")


class DoctrineInfo(BaseModel):
    """Informations doctrine (clé 'doctrine')."""
    model_config = ConfigDict(extra="allow")

    thematique: str = ""


class DocumentMetadata(BaseModel):
    """Métadonnées complètes d'un document (/api/document/metadata/{docId})."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(default="", alias="_id")
    creation_date: int | None = Field(default=None, alias="creationDate")
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    jurisprudence: JurisprudenceInfo | None = None
    encyclo: EncycloInfo | None = None
    revue: RevueInfo | None = None
    doctrine: DoctrineInfo | None = None
    from_field: str | None = Field(default=None, alias="from")


# --- Recherche ---

class SearchHitSource(BaseModel):
    """Contenu source d'un résultat de recherche."""
    model_config = ConfigDict(extra="allow")

    document: dict[str, Any] = Field(default_factory=dict)
    jurisprudence: dict[str, Any] | None = None
    revue: dict[str, Any] | None = None
    doctrine: dict[str, Any] | None = None
    news: dict[str, Any] | None = None
    taxo: dict[str, Any] | None = None
    encyclo: dict[str, Any] | None = None


class SearchHit(BaseModel):
    """Un résultat de recherche."""
    model_config = ConfigDict(extra="allow")

    id: str
    score: float = 0
    source: SearchHitSource = Field(default_factory=SearchHitSource)
    highlights: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.source.document.get("title", "")

    @property
    def doc_type(self) -> str:
        return self.source.document.get("type", "")

    @property
    def date(self) -> int | None:
        return self.source.document.get("date")

    @property
    def date_dt(self) -> datetime | None:
        return ms_to_datetime(self.date)


class CombiningInfo(BaseModel):
    """Informations de combining dans la réponse de recherche."""
    model_config = ConfigDict(extra="allow")

    last_combining_offset: int = Field(default=0, alias="lastCombiningOffset")
    nb_hits_collected: int = Field(default=0, alias="nbHitsCollected")
    combining_http_status: str = Field(default="", alias="combiningHttpStatus")
    has_combined: bool = Field(default=False, alias="hasCombined")


class NerNgram(BaseModel):
    """N-gram détecté par le service NER."""
    model_config = ConfigDict(extra="allow")

    score: float = 0
    start: int = 0
    end: int = 0
    text: str = ""


class SearchData(BaseModel):
    """Données de la réponse de recherche."""
    model_config = ConfigDict(extra="allow")

    total: int = 0
    total_text: str = Field(default="", alias="totalText")
    max_score: float = Field(default=0, alias="maxScore")
    hits: list[SearchHit] = Field(default_factory=list)
    combining: CombiningInfo | None = None
    ner_service: dict[str, Any] | None = Field(default=None, alias="ner_service")


class SearchResponse(BaseModel):
    """Réponse complète de /api/recherche//search."""
    model_config = ConfigDict(extra="allow")

    data: SearchData = Field(default_factory=SearchData)


# --- Navigation ---

class NavigationLinkMeta(BaseModel):
    """Métadonnées d'un lien de navigation."""
    model_config = ConfigDict(extra="allow")

    document: dict[str, Any] = Field(default_factory=dict)
    jurisprudence: dict[str, Any] | None = None
    encyclo: dict[str, Any] | None = None
    revue: dict[str, Any] | None = None


class NavigationLink(BaseModel):
    """Un lien dans le volet droit (navigation)."""
    model_config = ConfigDict(extra="allow")

    doc_id: str = Field(default="", alias="docId")
    title: str = ""
    type: str = ""
    date: int | None = None
    metas: NavigationLinkMeta | None = None

    @property
    def date_dt(self) -> datetime | None:
        return ms_to_datetime(self.date)


class NavigationSection(BaseModel):
    """Section du volet droit (liens groupés par type)."""
    model_config = ConfigDict(extra="allow")

    title: str = ""
    qualif: str | None = None
    direction: str | None = None
    ordre: int = 0
    links: list[NavigationLink] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    """Une entrée de la frise chronologique."""
    model_config = ConfigDict(extra="allow")

    doc_id: str | None = Field(default=None, alias="docId")
    doc_id_source: str | None = Field(default=None, alias="docIdSource")
    qualif: str = ""
    title: str | None = None
    label: str | None = None
    annee: int | None = None
    classe_juridiction: str = Field(default="", alias="classeJuridiction")
    classe_juridiction_code: str = Field(default="", alias="classeJuridictionCode")
    date: list[int] = Field(default_factory=list)
    numeros: list[str] = Field(default_factory=list)
    siege: str = ""
    direction: str = ""
    solution_label: str | None = Field(default=None, alias="solutionLabel")


class CodeTreeNode(BaseModel):
    """Noeud de l'arborescence d'un code."""
    model_config = ConfigDict(extra="allow")

    title: str = ""
    doc_id_stable: str = Field(default="", alias="doc_id_stable")
    indice: Any = None
    children: list[CodeTreeNode] = Field(default_factory=list)


class CodeTree(BaseModel):
    """Arborescence complète d'un code."""
    model_config = ConfigDict(extra="allow")

    title: str = ""
    doc_id_stable: str = Field(default="", alias="doc_id_stable")
    root: list[CodeTreeNode] = Field(default_factory=list)
