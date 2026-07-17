"""
Baixa os dados de demanda do S3 (bucket harumi-production-data-pipeline)
para data/raw/, preservando a estrutura de pastas do prefixo.

Uso:
  python src/main/download_demanda.py
  python src/main/download_demanda.py --dest data/raw --dry-run
  python src/main/download_demanda.py --prefix afm/processing/demanda/2025-12-10/
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import boto3

LOG_FMT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("download-demanda")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_BUCKET = "harumi-production-data-pipeline"
DEFAULT_PREFIX = "afm/processing/demanda/"
DEFAULT_DEST = BASE_DIR / "data" / "raw"


def iter_objects(s3_client, bucket: str, prefix: str):
    """Gera as chaves (key, size) de todos os objetos sob o prefixo, paginando."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue  # "pasta" vazia, sem conteúdo pra baixar
            yield key, obj["Size"]


def download_prefix(
    bucket: str,
    prefix: str,
    dest: Path,
    dry_run: bool = False,
    profile: str | None = None,
) -> None:
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    s3 = session.client("s3")

    dest.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_bytes = 0
    skipped = 0

    for key, size in iter_objects(s3, bucket, prefix):
        # espelha a estrutura do prefixo dentro de dest
        relative_key = key[len(prefix):] if key.startswith(prefix) else key
        local_path = dest / relative_key

        if local_path.exists() and local_path.stat().st_size == size:
            skipped += 1
            continue

        total_files += 1
        total_bytes += size

        if dry_run:
            logger.info(f"[dry-run] s3://{bucket}/{key} -> {local_path} ({size} bytes)")
            continue

        local_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"baixando s3://{bucket}/{key} -> {local_path}")
        s3.download_file(bucket, key, str(local_path))

    action = "seriam baixados" if dry_run else "baixados"
    logger.info(
        f"{total_files} arquivos {action} ({total_bytes / (1024 * 1024):.2f} MB)"
        f" | {skipped} já existentes, ignorados"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="Bucket S3.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Prefixo (pasta) dentro do bucket.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Diretório local de destino.")
    parser.add_argument("--profile", default=None, help="Profile do AWS CLI/credentials a usar.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Só lista o que seria baixado, sem gravar nada."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    download_prefix(
        bucket=args.bucket,
        prefix=args.prefix,
        dest=args.dest,
        dry_run=args.dry_run,
        profile=args.profile,
    )


if __name__ == "__main__":
    main()
