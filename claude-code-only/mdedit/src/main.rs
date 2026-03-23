use clap::{Parser, Subcommand};
use std::process;

mod error;
mod document;
mod parser;
mod addressing;
mod content;
mod counting;
mod output;
mod whitespace;
mod commands;

#[derive(Parser)]
#[command(name = "mdedit")]
#[command(about = "Structured markdown editing for LLM workflows")]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Section hierarchy with word counts
    Outline {
        file: String,
        #[arg(long)]
        max_depth: Option<u8>,
    },
    /// Pull section content (raw or to file)
    Extract {
        file: String,
        section: String,
        #[arg(long)]
        no_children: bool,
        #[arg(long)]
        to_file: Option<String>,
    },
    /// Find sections containing text
    Search {
        file: String,
        query: String,
        #[arg(long)]
        case_sensitive: bool,
    },
    /// Word/line counts per section
    Stats {
        file: String,
    },
    /// Check heading structure
    Validate {
        file: String,
    },
    /// Read/write YAML frontmatter
    Frontmatter {
        /// File path (used when no subcommand given, defaults to show)
        file: Option<String>,
        #[command(subcommand)]
        action: Option<FrontmatterAction>,
    },
    /// Substitute section content
    Replace {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        preserve_children: bool,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add content to end of section
    Append {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add content to start of section
    Prepend {
        file: String,
        section: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Add new section at position
    Insert {
        file: String,
        #[arg(long, required_unless_present = "before", conflicts_with = "before")]
        after: Option<String>,
        #[arg(long, required_unless_present = "after", conflicts_with = "after")]
        before: Option<String>,
        #[arg(long, required = true)]
        heading: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        from_file: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Remove section and content
    Delete {
        file: String,
        section: String,
        #[arg(long)]
        dry_run: bool,
    },
    /// Change heading text
    Rename {
        file: String,
        section: String,
        new_name: String,
        #[arg(long)]
        dry_run: bool,
    },
}

#[derive(Subcommand)]
enum FrontmatterAction {
    /// Show all frontmatter fields
    Show {
        file: String,
    },
    /// Get a specific frontmatter field value
    Get {
        file: String,
        key: String,
    },
    /// Set a frontmatter field value
    Set {
        file: String,
        key: String,
        value: String,
        #[arg(long)]
        dry_run: bool,
    },
    /// Delete a frontmatter field
    Delete {
        file: String,
        key: String,
        #[arg(long)]
        dry_run: bool,
    },
}

fn main() {
    let cli = Cli::parse();

    let result: Result<(), error::MdeditError> = match cli.command {
        Commands::Outline { file, max_depth } => {
            commands::outline::run(&file, max_depth)
        }
        Commands::Extract { file, section, no_children, to_file } => {
            commands::extract::run(&file, &section, no_children, to_file.as_deref())
        }
        Commands::Search { file, query, case_sensitive } => {
            commands::search::run(&file, &query, case_sensitive)
        }
        Commands::Stats { file } => {
            commands::stats::run(&file)
        }
        Commands::Validate { file } => {
            commands::validate::run(&file)
        }
        Commands::Frontmatter { file, action } => match action {
            Some(FrontmatterAction::Show { file }) => {
                commands::frontmatter::run_show(&file)
            }
            Some(FrontmatterAction::Get { file, key }) => {
                commands::frontmatter::run_get(&file, &key)
            }
            Some(FrontmatterAction::Set { file, key, value, dry_run }) => {
                commands::frontmatter::run_set(&file, &key, &value, dry_run)
            }
            Some(FrontmatterAction::Delete { file, key, dry_run }) => {
                commands::frontmatter::run_delete(&file, &key, dry_run)
            }
            None => match file {
                Some(f) => commands::frontmatter::run_show(&f),
                None => Err(error::MdeditError::InvalidOperation(
                    "file required: mdedit frontmatter <file>".to_string()
                )),
            }
        },
        Commands::Replace { file, section, content, from_file, preserve_children, dry_run } => {
            commands::replace::run(
                &file,
                &section,
                content.as_deref(),
                from_file.as_deref(),
                preserve_children,
                dry_run,
            )
        }
        Commands::Append { file, section, content, from_file, dry_run } => {
            commands::append::run(
                &file,
                &section,
                content.as_deref(),
                from_file.as_deref(),
                dry_run,
            )
        }
        Commands::Prepend { file, section, content, from_file, dry_run } => {
            commands::prepend::run(
                &file,
                &section,
                content.as_deref(),
                from_file.as_deref(),
                dry_run,
            )
        }
        Commands::Insert { file, after, before, heading, content, from_file, dry_run } => {
            commands::insert::run(
                &file,
                after.as_deref(),
                before.as_deref(),
                &heading,
                content.as_deref(),
                from_file.as_deref(),
                dry_run,
            )
        }
        Commands::Delete { file, section, dry_run } => {
            commands::delete::run(&file, &section, dry_run)
        }
        Commands::Rename { file, section, new_name, dry_run } => {
            commands::rename::run(&file, &section, &new_name, dry_run)
        }
    };

    if let Err(e) = result {
        match &e {
            error::MdeditError::NoOp(_) => {
                // NoOp is informational — print to stdout, not stderr
                println!("{}", e);
            }
            _ => {
                eprintln!("{}", e);
            }
        }
        process::exit(e.exit_code());
    }
}
