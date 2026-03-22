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
        /// File to operate on
        file: String,
        /// Subcommand: get, set, or delete (omit to show all fields)
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
    /// Get a frontmatter field value
    Get {
        key: String,
    },
    /// Set a frontmatter field value
    Set {
        key: String,
        value: String,
        #[arg(long)]
        dry_run: bool,
    },
    /// Delete a frontmatter field
    Delete {
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
        _ => {
            eprintln!("Command not yet implemented");
            process::exit(1);
        }
    };

    if let Err(e) = result {
        eprintln!("{}", e);
        process::exit(e.exit_code());
    }
}
